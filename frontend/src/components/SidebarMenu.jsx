import { useState } from "react";

const sidebarMenus = [
  { id: "dashboard", label: "대시보드" },
  {
    id: "reports",
    label: "보고서",
    children: ["제조사별 점유율 현황", "품목별 점유율 현황", "종합쇼핑몰 등록 내역"],
  },
  { id: "products", label: "상품조회" },
  {
    id: "orders",
    label: "발주현황",
    children: ["발주 현황", "발주 현황(달력)", "발주 현황(월별)"],
  },
  {
    id: "inventory",
    label: "재고 현황",
    children: ["위탁점 재고현황"],
  },
  { id: "settlement", label: "정산 현황" },
];

export default function SidebarMenu({ activeMenu, onSelect }) {
  const [expanded, setExpanded] = useState({
    reports: true,
    orders: true,
    inventory: true,
  });

  const toggleExpand = (id) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <aside className="w-full md:w-[260px] bg-white border border-brand-200 rounded-xl p-4 shadow-sm h-fit">
      <p className="text-xs text-slate-400 font-semibold mb-3">메뉴</p>
      <nav className="space-y-1">
        {sidebarMenus.map((menu) => {
          const isParentOpen = expanded[menu.id];
          const isActiveTop = activeMenu === menu.label;
          const hasChildren = Array.isArray(menu.children);

          return (
            <div key={menu.id}>
              <button
                type="button"
                onClick={() => {
                  onSelect(menu.label);
                  if (hasChildren) toggleExpand(menu.id);
                }}
                className={`w-full flex items-center justify-between px-2.5 py-2 rounded-md text-left text-[15px] font-semibold ${
                  isActiveTop
                    ? "bg-brand-100 text-brand-700"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                <span>{menu.label}</span>
                {hasChildren ? <span className="text-xs">{isParentOpen ? "v" : ">"}</span> : null}
              </button>

              {hasChildren && isParentOpen ? (
                <div className="ml-3 mt-1 space-y-0.5 border-l border-slate-200 pl-3">
                  {menu.children.map((child) => {
                    const isActiveChild = activeMenu === child;
                    return (
                      <button
                        key={child}
                        type="button"
                        onClick={() => onSelect(child)}
                        className={`w-full px-2 py-1.5 rounded-md text-left text-sm ${
                          isActiveChild
                            ? "bg-brand-100 text-brand-700 font-semibold"
                            : "text-slate-600 hover:bg-slate-100"
                        }`}
                      >
                        {child}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
