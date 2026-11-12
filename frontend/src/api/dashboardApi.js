import axios from "axios";

const API_BASE = import.meta.env.DEV ? "http://localhost:8000/api" : "/api";

function toYYYYMMDD(dateValue) {
  return String(dateValue || "").replaceAll("-", "");
}

function searchParams(params) {
  return {
    startDate: toYYYYMMDD(params.start_date),
    endDate: toYYYYMMDD(params.end_date),
    category: params.category || "",
    company: params.company || "",
    productName: params.product_name || "",
  };
}

export async function fetchMarketShare(params) {
  const { data } = await axios.get(`${API_BASE}/dashboard`, { params: searchParams(params) });
  return data;
}

export async function fetchRegistrations(params, page, pageSize) {
  const { data } = await axios.get(`${API_BASE}/registrations`, {
    params: { ...searchParams(params), page, pageSize },
  });
  return data;
}

export function downloadRegistrationsExcel(params) {
  const query = new URLSearchParams(searchParams(params)).toString();
  window.open(`${API_BASE}/registrations/excel?${query}`, "_blank");
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

async function syncPage(path, params) {
  const query = {
    startDate: toYYYYMMDD(params.start_date),
    endDate: toYYYYMMDD(params.end_date),
    category: params.category || "",
    step: true,
    force: Boolean(params.refresh),
  };
  const { data } = await axios.post(`${API_BASE}/${path}/sync`, null, { params: query });
  return data;
}

export const syncDashboardCache = params => syncPage("dashboard", params);
export const syncRegistrations = params => syncPage("registrations", params);

export async function fetchDashboardUsage() {
  const { data } = await axios.get(`${API_BASE}/dashboard/usage`);
  return data;
}
