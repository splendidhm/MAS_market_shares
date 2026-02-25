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
const defaultDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(
  today.getDate()
).padStart(2, "0")}`;

export default function App() {
  const [filters, setFilters] = useState({
    start_date: defaultDate,
    end_date: defaultDate,
    category: "",
    company: "",
    product_name: "",
    top_n: 10,
  });
  const [rows, setRows] = useState([]);
  const [chartRows, setChartRows] = useState([]);
  const [totalAmount, setTotalAmount] = useState(0);
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
  const [activeMenu, setActiveMenu] = useState("대시보드");

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

  const onSearch = async () => {
    setLoading(true);
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
      setChartRows(normalizedChart);
      setTotalAmount(result.total_amount || 0);
      setCacheHit(Boolean(result.cache_hit));
      await loadUsage();
    } catch (e) {
      const message = e?.response?.data?.detail || "조회 중 오류가 발생했습니다.";
      setError(message);
      setRows([]);
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
    setSyncing(true);
    setError("");
    setWarning("");
    try {
      const syncResult = await syncDashboardCache(filters);
      if (syncResult?.warning_message) {
        setWarning(syncResult.warning_message);
      }
      await loadUsage();
      await onSearch();
    } catch (e) {
      const message = e?.response?.data?.detail || "DB 동기화 중 오류가 발생했습니다.";
      setError(message);
    } finally {
      setSyncing(false);
    }
  };

  const statusMessage = useMemo(() => {
    if (loading) return "데이터 조회 중...";
    if (syncing) return "DB 동기화 중...";
    if (warning) return warning;
    if (error) return `오류: ${error}`;
    if (!rows.length) return "DB 데이터가 없습니다. 먼저 'DB 동기화'를 실행해주세요.";
    return cacheHit ? "DB 캐시 데이터 조회 완료" : "DB 조회 완료";
  }, [loading, syncing, warning, error, rows.length, cacheHit]);

  return (
    <div className="max-w-[1460px] mx-auto px-4 py-6">
      <div className="flex flex-col md:flex-row gap-4">
        <SidebarMenu activeMenu={activeMenu} onSelect={setActiveMenu} />

        <main className="flex-1 space-y-4">
          <header className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm text-center">
            <p className="text-brand-700 text-lg font-semibold">
              조달청 식품 품목 시장점유율 대시보드
            </p>
          </header>

          <div className="bg-brand-50 border border-brand-200 rounded-lg px-4 py-2 text-sm text-brand-700 font-semibold">
            현재 선택 메뉴: {activeMenu}
          </div>

          <div className="bg-white border border-brand-200 rounded-lg px-4 py-2 text-sm text-brand-700 font-semibold">
            오늘 API 사용량: {usage.daily_call_count} / {usage.daily_call_limit}
            {" · "}남은 호출: {usage.remaining_calls}
          </div>

          <Filters
            filters={filters}
            setFilters={setFilters}
            onSearch={onSearch}
            onExcel={onExcel}
            onSync={onSync}
          />

          <div className="bg-brand-100 text-[#0c4a6e] rounded-lg px-4 py-2 text-sm font-semibold">
            {statusMessage}
          </div>

          <div className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm text-brand-700 font-semibold">
            전체 납품금액 합계: {Number(totalAmount).toLocaleString()} 원
          </div>

          <TopManufacturersChart data={chartRows} />
          <MarketShareTable rows={rows} />
        </main>
      </div>
    </div>
  );
}
