const menus = [
  ["sales", "제조사별 매출 현황 조회"],
  ["registration", "나라장터 품목등록 내역 조회"],
];

export default function SidebarMenu({ activeMenu, onSelect }) {
  return (
    <aside className="w-full md:w-[260px] bg-white border border-brand-200 rounded-xl p-4 shadow-sm h-fit">
      <h2 id="dashboard-menu" className="font-semibold mb-3">대시보드</h2>
      <nav aria-labelledby="dashboard-menu" className="space-y-1">
        {menus.map(([id, label]) => (
          <button key={id} type="button" onClick={() => onSelect(id)}
            aria-current={activeMenu === id ? "page" : undefined}
            className={`w-full px-2.5 py-2 rounded-md text-left text-sm ${activeMenu === id
              ? "bg-brand-100 text-brand-700 font-semibold"
              : "text-slate-600 hover:bg-slate-100"}`}>
            {label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
