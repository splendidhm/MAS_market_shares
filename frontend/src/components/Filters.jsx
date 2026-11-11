import React from "react";

const categories = [
  "전체", "김치", "고추장", "국탕류", "냉동감자", "냉동만두", "밀가루",
  "소시지류", "수산물가공품", "식육가공품", "장류", "즉석조리식품",
  "축산가공품", "조미김", "혼합장", "떡", "면류", "발효유", "빵류", "과자류",
];

function setPeriod(prev, period, value) {
  const year = value.split("-")[0];
  const month = value.split("-").slice(0,2).join("-");
  if (period === "year") return {...prev, period, start_date: year + "-01-01", end_date: year + "-12-31"};
  if (period === "month" && month.includes("-")) {
    const last = new Date(Number(year), Number(month.split("-")[1]), 0).getDate();
    return {...prev, period, start_date: month + "-01", end_date: month + "-" + last};
  }
  return {...prev, period, start_date: value, end_date: period === "day" ? value : prev.end_date};
}

export default function Filters({ categoriesFound, filters, setFilters, onSearch, onExcel, onSync }) {
  return (
    <div className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label>기간 단위 <select aria-label="기간 단위" className="bg-white border border-brand-500 rounded px-2 py-1" value={filters.period || "range"} onChange={e => {
          const period = e.target.value;
          setFilters(prev => setPeriod(prev, period, prev.start_date));
        }}><option value="range">직접 지정</option><option value="day">일</option><option value="month">월</option><option value="year">년</option></select></label>
        {["month","year"].includes(filters.period) && <label>연도 <input aria-label="조회 연도" type="number" min="1" max="9999"
          className="w-20 border rounded px-2" value={filters.start_date.split("-")[0]} onChange={e => {
            const value = e.target.value + filters.start_date.slice(-6);
            setFilters(setPeriod(filters, filters.period, value));
          }} /></label>}
        {filters.period === "month" && <label>월 <select aria-label="조회 월" className="bg-white border border-brand-500 rounded px-2 py-1" value={filters.start_date.slice(5,7)}
          onChange={e => setFilters(setPeriod(filters, "month", filters.start_date.slice(0,5) + e.target.value))}>
          {Array.from({length: 12}, (_, i) => String(i+1).padStart(2,"0")).map(m => <option key={m} value={m}>{Number(m)}월</option>)}
        </select></label>}
        <label><input type="checkbox" checked={Boolean(filters.refresh)} onChange={e => setFilters(prev => ({...prev, refresh: e.target.checked}))}/> 완료 자료도 다시 수집</label>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
        <input
          type="date"
          disabled={["year","month"].includes(filters.period)}
          value={filters.start_date}
          onChange={(e) => setFilters((prev) => setPeriod(prev, prev.period, e.target.value))}
          className="border border-brand-200 rounded-lg px-3 py-2"
        />
        <input
          type="date"
          disabled={["year","month","day"].includes(filters.period)}
          value={filters.end_date}
          onChange={(e) => setFilters((prev) => ({ ...prev, end_date: e.target.value }))}
          className="border border-brand-200 rounded-lg px-3 py-2"
        />
        <input
          placeholder="납품업체 검색"
          value={filters.company}
          onChange={(e) =>
            setFilters((prev) => ({ ...prev, company: e.target.value }))
          }
          className="border border-brand-200 rounded-lg px-3 py-2"
        />
        <input
          placeholder="제품명 검색"
          value={filters.product_name}
          onChange={(e) =>
            setFilters((prev) => ({ ...prev, product_name: e.target.value }))
          }
          className="border border-brand-200 rounded-lg px-3 py-2"
        />
        <div className="flex gap-2 md:col-span-2">
          <button
            onClick={onSync}
            className="flex-1 bg-white text-brand-700 border border-brand-200 rounded-lg px-3 py-2 font-semibold hover:bg-brand-100"
          >
            DB 동기화
          </button>
          <button
            onClick={onSearch}
            className="flex-1 bg-brand-500 text-white rounded-lg px-3 py-2 font-semibold hover:bg-brand-700"
          >
            조회
          </button>
          <button
            onClick={onExcel}
            className="flex-1 bg-white text-brand-700 border border-brand-200 rounded-lg px-2 py-2 text-xs leading-none font-semibold whitespace-nowrap hover:bg-brand-100"
          >
            엑셀 다운로드
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {categoriesFound.length > 0 && <select aria-label="수집된 식품 분류" value={categoriesFound.includes(filters.category) ? filters.category : ""} onChange={e => setFilters({...filters, category:e.target.value})}>
          <option value="">수집된 식품 분류 전체</option>{categoriesFound.map(name => <option key={name}>{name}</option>)}
        </select>}
        <input aria-label="식품 품명 직접 입력" placeholder="식품 품명 직접 입력" value={filters.category || ""} onChange={e => setFilters(prev => ({...prev, category:e.target.value}))} className="border rounded px-2" />
        {categories.map((category) => (
          <button
            key={category}
            aria-pressed={filters.category === (category === "전체" ? "" : category)}
            onClick={() => setFilters((prev) => ({ ...prev, category: category === "전체" ? "" : category }))}
            className={`px-3 py-1.5 rounded-full border text-sm font-semibold ${
              filters.category === (category === "전체" ? "" : category)
                ? "bg-brand-500 text-white border-brand-500"
                : "bg-white text-brand-700 border-brand-200 hover:bg-brand-100"
            }`}
          >
            {category}
          </button>
        ))}
      </div>

    </div>
  );
}
