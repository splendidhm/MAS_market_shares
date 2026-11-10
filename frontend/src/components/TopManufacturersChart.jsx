import React from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function TopManufacturersChart({ data }) {
  return (
    <div className="bg-white border border-brand-200 rounded-xl p-4 shadow-sm">
      <h3 className="text-brand-700 font-bold text-lg mb-3">Top 10 납품업체 점유율</h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="company" />
            <YAxis unit="%" />
            <Tooltip formatter={(value) => `${value}%`} />
            <Bar dataKey="share" fill="#0ea5e9" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
