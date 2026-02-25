import axios from "axios";

const API_BASE = "http://localhost:8000/api";

function toYYYYMMDD(dateValue) {
  return String(dateValue || "").replaceAll("-", "");
}

export async function fetchMarketShare(params) {
  const query = {
    startDate: toYYYYMMDD(params.start_date),
    endDate: toYYYYMMDD(params.end_date),
    category: params.category || "",
    company: params.company || "",
    productName: params.product_name || "",
  };
  const { data } = await axios.get(`${API_BASE}/dashboard`, { params: query });
  return data;
}

export function downloadExcel(params) {
  const query = new URLSearchParams({
    startDate: toYYYYMMDD(params.start_date),
    endDate: toYYYYMMDD(params.end_date),
    category: params.category || "",
    company: params.company || "",
    productName: params.product_name || "",
  }).toString();
  window.open(`${API_BASE}/dashboard/excel?${query}`, "_blank");
}

export async function syncDashboardCache(params) {
  const query = {
    startDate: toYYYYMMDD(params.start_date),
    endDate: toYYYYMMDD(params.end_date),
    force: false,
  };
  const { data } = await axios.post(`${API_BASE}/dashboard/sync`, null, { params: query });
  return data;
}

export async function fetchDashboardUsage() {
  const { data } = await axios.get(`${API_BASE}/dashboard/usage`);
  return data;
}
