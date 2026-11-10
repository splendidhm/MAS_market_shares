import React from "react";

const headers = [
  "순위",
  "납품업체",
  "금액",
  "점유율",
  "누적점유율",
];

export default function MarketShareTable({ rows }) {
  return (
    <div className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm overflow-auto">
      <table className="min-w-full text-sm">
        <thead className="bg-brand-50">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 text-left text-brand-700 font-semibold whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`${row.company}-${idx}`} className="border-t border-brand-100">
              <td className="px-3 py-2">{row.rank}</td>
              <td className="px-3 py-2">{row.company}</td>
              <td className="px-3 py-2">{Number(row.amount).toLocaleString()}</td>
              <td className="px-3 py-2">{row.share}%</td>
              <td className="px-3 py-2">{row.cumulative_share}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
