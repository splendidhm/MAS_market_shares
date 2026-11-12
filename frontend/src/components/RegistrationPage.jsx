import { useEffect, useState } from "react";
import {
  downloadRegistrationsExcel,
  fetchRegistrations,
  syncRegistrations,
} from "../api/dashboardApi";
import Filters from "./Filters";

const pageSize = 50;
const columns = [
  ["rgstDt", "등록일"], ["prdctIdntNo", "물품식별번호"], ["dtilPrdctClsfcNoNm", "세부품명"],
  ["prdctSpecNm", "물품규격명"], ["cntrctCorpNm", "계약업체"], ["prdctMakrNm", "제조사"],
  ["cntrctPrceAmt", "계약단가(원)"], ["prdctUnit", "단위"], ["shopngCntrctNo", "쇼핑계약번호"],
];

function displayDate(value) {
  return String(value || "").replace(/^(\d{4})(\d{2})(\d{2})$/, "$1-$2-$3");
}

function cellValue(field, value) {
  if (value == null || value === "") return "—";
  if (field === "rgstDt") return displayDate(value);
  if (field === "cntrctPrceAmt") return Number(value).toLocaleString("ko-KR");
  return value;
}

export default function RegistrationPage({ startDate, endDate, usage, loadUsage }) {
  const [filters, setFilters] = useState({
    period: "month", start_date: startDate, end_date: endDate, category: "", company: "", product_name: "",
  });
  const [categories, setCategories] = useState([]);
  const [result, setResult] = useState(null);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState("");
  const [syncState, setSyncState] = useState(null);
  const [pageHistory, setPageHistory] = useState([]);

  useEffect(() => {
    setResult(null);
    setPage(1);
    setMessage("");
    setSyncState(null);
    setPageHistory([]);
  }, [filters.start_date, filters.end_date, filters.category, filters.company, filters.product_name]);

  async function query(nextPage = 1, sync = false) {
    if (busy) return;
    if (!filters.start_date || !filters.end_date || filters.start_date > filters.end_date) {
      setMessage("시작일과 종료일을 확인해주세요.");
      return;
    }
    setBusy(true);
    setSyncing(sync);
    setMessage(sync ? "첫 페이지 수집 중…" : "등록 내역 조회 중…");
    if (sync) {
      setSyncState(null);
      setPageHistory([]);
    }
    try {
      if (sync) {
        let state;
        do {
          state = await syncRegistrations({ ...filters, refresh: !state && filters.refresh });
          setSyncState(state);
          setMessage(state.progress);
          if (state.current_page) {
            setPageHistory((previous) => [...previous, state]);
          }
          await new Promise((resolve) => setTimeout(resolve, 0));
        } while (!state.complete);
      }
      const data = await fetchRegistrations(filters, nextPage, pageSize);
      setResult(data);
      setPage(nextPage);
      if (data.complete && !filters.category) setCategories(data.categories);
      setMessage(data.complete
        ? `${displayDate(data.through)}까지 조회 · 식품 등록 내역 ${data.total.toLocaleString()}건`
        : "이 기간과 식품의 등록 내역을 먼저 DB 동기화해주세요.");
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setResult(null);
      setMessage(typeof detail === "string" ? detail : "등록 내역을 조회하지 못했습니다. 다시 시도해주세요.");
    } finally {
      if (sync) await loadUsage();
      setBusy(false);
      setSyncing(false);
    }
  }

  const pages = Math.ceil((result?.total || 0) / pageSize);
  const progressPercent = syncState?.expected
    ? Math.min(100, Math.round(syncState.scanned * 100 / syncState.expected))
    : syncState?.complete ? 100 : 0;
  return (
    <div className="space-y-4">
      <header className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm text-center">
        <h1 className="text-brand-700 text-lg font-semibold">나라장터 품목등록 내역 조회</h1>
      </header>
      <div className="bg-white border border-brand-200 rounded-lg px-4 py-2 text-sm text-brand-700 font-semibold">
        오늘 API 사용량: {usage.daily_call_count} / {usage.daily_call_limit} · 남은 호출: {usage.remaining_calls}
      </div>
      <fieldset disabled={busy}>
        <Filters categoriesFound={categories} filters={filters} setFilters={setFilters}
          companyLabel="계약업체·제조사 검색" productLabel="물품규격명·식별번호 검색"
          onSearch={() => query()} onSync={() => query(1, true)}
          onExcel={() => downloadRegistrationsExcel(filters)} />
      </fieldset>
      <p role="status" className="bg-brand-100 text-brand-700 rounded-lg px-4 py-2 text-sm font-semibold">
        {message || "등록일 기준으로 어제까지 제공됩니다. 기간과 식품을 선택해주세요."}
      </p>
      {(syncing || pageHistory.length > 0) && (
        <section aria-label="페이지별 수집 현황"
          className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold text-brand-700">페이지별 수집 현황</h2>
            {syncState?.current_page > 0 && (
              <span className="text-sm font-semibold text-brand-700">
                {syncState.period_index} / {syncState.period_count} 기간 ·
                {" "}{syncState.current_page} / {syncState.total_pages} 페이지
              </span>
            )}
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-brand-100"
            role="progressbar" aria-label="현재 기간 원천 수집률"
            aria-valuemin="0" aria-valuemax="100" aria-valuenow={progressPercent}>
            <div className="h-full rounded-full bg-brand-500 transition-all duration-200"
              style={{ width: `${progressPercent}%` }} />
          </div>
          <p className="text-sm text-slate-700">
            {syncState?.progress || "조달청 첫 페이지 응답을 기다리는 중입니다."}
          </p>
          {pageHistory.length > 0 && (
            <ol className="max-h-48 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100">
              {pageHistory.map((state, index) => (
                <li key={`${state.period_start}-${state.period_end}-${state.current_page}-${index}`}
                  className="grid grid-cols-1 gap-1 px-3 py-2 text-sm md:grid-cols-[1fr_auto_auto]">
                  <span>{displayDate(state.period_start)} ~ {displayDate(state.period_end)}</span>
                  <span className="font-semibold">
                    {state.current_page} / {state.total_pages} 페이지
                  </span>
                  <span className="text-slate-600">
                    원천 {Number(state.scanned).toLocaleString()} / {Number(state.expected).toLocaleString()}건
                    {" · "}이번 페이지 원천 {Number(state.page_rows).toLocaleString()}건
                    {" / "}식품 {Number(state.food_rows).toLocaleString()}건
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
      {result?.complete && result.total > 0 && (
        <section className="bg-white border rounded-xl p-4">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">나라장터 식품 품목등록 내역</caption>
              <thead><tr>{columns.map(([field, label]) =>
                <th scope="col" key={field} className="p-2 text-left whitespace-nowrap">{label}</th>)}</tr></thead>
              <tbody>{result.rows.map((row, i) => <tr key={i} className="border-t align-top">
                {columns.map(([field]) => <td key={field} className={field === "prdctSpecNm"
                  ? "p-2 min-w-64" : "p-2 whitespace-nowrap"}>{cellValue(field, row[field])}</td>)}
              </tr>)}</tbody>
            </table>
          </div>
          {pages > 1 && <nav aria-label="등록 내역 페이지" className="flex gap-3 items-center mt-3 text-sm">
            <button disabled={busy || page === 1} onClick={() => query(page - 1)}>이전</button>
            <span>{page} / {pages}</span>
            <button disabled={busy || page >= pages} onClick={() => query(page + 1)}>다음</button>
          </nav>}
        </section>
      )}
    </div>
  );
}
