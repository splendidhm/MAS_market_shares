import { useEffect, useMemo, useState } from "react";
import Filters from "./components/Filters";
import MarketShareTable from "./components/MarketShareTable";
import TopManufacturersChart from "./components/TopManufacturersChart";
import SidebarMenu from "./components/SidebarMenu";
import {
  downloadExcel,
  fetchDashboardUsage,
  fetchMarketShare,
  syncDashboardCache,
} from "./api/dashboardApi";

const today = new Date();
const defaultMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
const defaultStartDate = `${defaultMonth}-01`;
const defaultEndDate = `${defaultMonth}-${String(
  new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
).padStart(2, "0")}`;

function ProductTable({ displayProducts, itemOnly = false, productPage, setPage }) {
  const pageSize = 50;
  const lastPage = Math.max(0, Math.ceil(displayProducts.length / pageSize) - 1);
  const visiblePage = Math.min(productPage, lastPage);

  return (
    <section className="bg-white border rounded-xl p-4 overflow-auto">
      <h2 className="font-semibold mb-2">{itemOnly ? "품목별 납품액" : "업체별 품목 납품액"}</h2>
      <table className="w-full text-sm"><thead><tr>{(itemOnly ? ["물품식별번호","품목","납품요구 순액(원)"] : ["업체","물품식별번호","품목","납품요구 순액(원)"]).map(h => <th key={h} className="text-left p-2">{h}</th>)}</tr></thead>
        <tbody>{displayProducts.slice(visiblePage * pageSize, (visiblePage + 1) * pageSize).map(r => <tr key={JSON.stringify([r.company,r.code,r.product])} className="border-t">{!itemOnly && <td>{r.company}</td>}<td>{r.code}</td><td>{r.product}</td><td>{r.amount.toLocaleString()}</td></tr>)}</tbody>
      </table>
      {lastPage > 0 && <div className="flex gap-3 items-center mt-3 text-sm">
        <button disabled={visiblePage === 0} onClick={() => setPage(visiblePage - 1)}>이전</button>
        <span>{visiblePage + 1} / {lastPage + 1} · {displayProducts.length.toLocaleString()}건</span>
        <button disabled={visiblePage === lastPage} onClick={() => setPage(visiblePage + 1)}>다음</button>
      </div>}
    </section>
  );
}

export default function App() {
  const [filters, setFilters] = useState({
    period: "month",
    start_date: defaultStartDate,
    end_date: defaultEndDate,
    category: "",
    company: "",
    product_name: "",
    top_n: 10,
  });
  const [rows, setRows] = useState([]);
  const [chartRows, setChartRows] = useState([]);
  const [totalAmount, setTotalAmount] = useState(0);
  const [categories, setCategories] = useState([]);
  const [itemRows, setItemRows] = useState([]);
  const [productPage, setProductPage] = useState(0);
  const [itemPage, setItemPage] = useState(0);
  const [products, setProducts] = useState([]);
  const [coverage, setCoverage] = useState(null);
  const [progress, setProgress] = useState("");
  const [cacheHit, setCacheHit] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [usage, setUsage] = useState({
    daily_call_count: 0,
    daily_call_limit: 900,
    remaining_calls: 900,
  });
  const [activeMenu, setActiveMenu] = useState("sales");

  const loadUsage = async () => {
    try {
      const usageData = await fetchDashboardUsage();
      setUsage({
        daily_call_count: usageData?.daily_call_count ?? 0,
        daily_call_limit: usageData?.daily_call_limit ?? 900,
        remaining_calls: usageData?.remaining_calls ?? 0,
      });
      if (usageData?.warning_message) {
        setWarning(usageData.warning_message);
      }
    } catch {
      // 사용량 조회 실패는 화면 주 기능에 영향이 없으므로 무시
    }
  };

  useEffect(() => {
    loadUsage();
  }, []);

  useEffect(() => {
    setCoverage(null);
    setRows([]);
    setProducts([]);
    setItemRows([]);
    setProductPage(0);
    setItemPage(0);
    setChartRows([]);
    setWarning("");
    setError("");
  }, [filters.start_date, filters.end_date, filters.category, filters.product_name, filters.company]);

  const onSearch = async () => {
    setLoading(true);
    setWarning("");
    setError("");
    try {
      const result = await fetchMarketShare(filters);
      const normalizedRows = (result.company_rank || []).map((row) => ({
        rank: row.rank,
        company: row.company,
        amount: row.amount,
        share: row.share,
        cumulative_share: row.cumulative_share,
      }));
      const normalizedChart = (result.chart_data || []).map((row) => ({
        company: row.company,
        share: row.share,
      }));
      setRows(normalizedRows);
      setProducts(result.product_rows || []);
      setItemRows(result.item_rows || []);
      setProductPage(0);
      setItemPage(0);
      if (result.complete && !filters.category) setCategories(result.categories || []);
      setCoverage(result.complete);
      setChartRows(normalizedChart);
      setTotalAmount(result.total_amount || 0);
      setCacheHit(Boolean(result.cache_hit));
      await loadUsage();
    } catch (e) {
      const message = e?.response?.data?.detail || "조회 중 오류가 발생했습니다.";
      setError(message);
      setRows([]);
      setProducts([]);
    setItemRows([]);
    setProductPage(0);
    setItemPage(0);
      setCoverage(null);
      setChartRows([]);
      setTotalAmount(0);
    } finally {
      setLoading(false);
    }
  };

  const onExcel = () => {
    downloadExcel(filters);
  };

  const onSync = async () => {
    if (syncing) return;
    setSyncing(true);
    setProgress("첫 페이지 확인 중");
    setError("");
    setWarning("");
    try {
      let result;
      do {
        result = await syncDashboardCache({...filters, refresh: !result && filters.refresh});
        setProgress(result.progress);
      } while (!result.complete);
      await loadUsage();
      await onSearch();
    } catch (e) {
      const message = e?.response?.data?.detail || "DB 동기화 중 오류가 발생했습니다.";
      setError(message);
      await loadUsage();
    } finally {
      setSyncing(false);
    }
  };

  const statusMessage = useMemo(() => {
    if (loading) return "데이터 조회 중...";
    if (syncing) return progress || "DB 동기화 중...";
    if (warning) return warning;
    if (error) return `오류: ${error}`;
    if (coverage === false) return "선택 기간·품목의 수집이 필요합니다. DB 동기화를 누르면 마지막 저장 페이지부터 이어받습니다.";
    if (coverage === null) return "기간과 식품을 선택한 뒤 조회하세요.";
    if (!rows.length) return "수집 완료 · 선택한 조건의 식품 납품내역이 없습니다.";
    return cacheHit ? "DB 캐시 데이터 조회 완료" : "DB 조회 완료";
  }, [loading, syncing, warning, error, rows.length, cacheHit, coverage, progress]);

  return (
    <div className="max-w-[1460px] mx-auto px-4 py-6">
      <div className="flex flex-col md:flex-row gap-4">
        <SidebarMenu activeMenu={activeMenu} onSelect={setActiveMenu} />

        <main className="flex-1 space-y-4">
          {activeMenu === "sales" && <>
          <header className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm text-center">
            <p className="text-brand-700 text-lg font-semibold">
              제조사별 매출 현황 조회
            </p>
          </header>

          <div className="bg-white border border-brand-200 rounded-lg px-4 py-2 text-sm text-brand-700 font-semibold">
            오늘 API 사용량: {usage.daily_call_count} / {usage.daily_call_limit}
            {" · "}남은 호출: {usage.remaining_calls}
          </div>

          <fieldset disabled={syncing || loading}><Filters
            categoriesFound={categories}
            filters={filters}
            setFilters={setFilters}
            onSearch={onSearch}
            onExcel={onExcel}
            onSync={onSync}
          /></fieldset>

          <div className="bg-brand-100 text-[#0c4a6e] rounded-lg px-4 py-2 text-sm font-semibold">
            {statusMessage}
          </div>

          <div className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm text-brand-700 font-semibold">
            식품 납품요구 순액(증감 반영): {coverage === true ? Number(totalAmount).toLocaleString() + " 원" : "—"}
          </div>

          <TopManufacturersChart data={chartRows} />
          <MarketShareTable rows={rows} />
          <ProductTable displayProducts={products} productPage={productPage} setPage={setProductPage} />
          <ProductTable displayProducts={itemRows} itemOnly productPage={itemPage} setPage={setItemPage} />
          </>}
        </main>
      </div>
    </div>
  );
}
