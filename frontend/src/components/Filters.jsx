import React from "react";

const categories = [
  { code: "", label: "전체" },
  { code: "50467001", label: "김치" },
  { code: "50171550", label: "고추장" },
  { code: "50191507", label: "국탕류" },
  { code: "50192602", label: "냉동감자" },
  { code: "50192602", label: "냉동만두" },
  { code: "50181901", label: "밀가루" },
  { code: "50112099", label: "소시지류" },
  { code: "50121598", label: "수산물가공품" },
  { code: "50112099", label: "식육가공품" },
  { code: "50171550", label: "장류" },
  { code: "50192602", label: "즉석조리식품" },
  { code: "50112099", label: "축산가공품" },
  { code: "50121539", label: "조미김" },
  { code: "50171550", label: "혼합장" },
  { code: "50182005", label: "떡" },
  { code: "50192902", label: "면류" },
  { code: "50131702", label: "발효유" },
  { code: "50181905", label: "빵류" },
  { code: "50181906", label: "과자류" },
];

export default function Filters({ filters, setFilters, onSearch, onExcel, onSync }) {
  return (
    <div className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-6 gap-3">
        <input
          type="date"
          value={filters.start_date}
          onChange={(e) => setFilters((prev) => ({ ...prev, start_date: e.target.value }))}
          className="border border-brand-200 rounded-lg px-3 py-2"
        />
        <input
          type="date"
          value={filters.end_date}
          onChange={(e) => setFilters((prev) => ({ ...prev, end_date: e.target.value }))}
          className="border border-brand-200 rounded-lg px-3 py-2"
        />
        <input
          placeholder="제조사 검색"
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
            className="flex-1 bg-white text-brand-700 border border-brand-200 rounded-lg px-3 py-2 font-semibold hover:bg-brand-100"
          >
            엑셀 다운로드
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {categories.map((category) => (
          <button
            key={`${category.label}-${category.code || "all"}`}
            onClick={() => setFilters((prev) => ({ ...prev, category: category.code }))}
            className={`px-3 py-1.5 rounded-full border text-sm font-semibold ${
              filters.category === category.code
                ? "bg-brand-500 text-white border-brand-500"
                : "bg-white text-brand-700 border-brand-200 hover:bg-brand-100"
            }`}
          >
            {category.label}
          </button>
        ))}
      </div>

    </div>
  );
}
