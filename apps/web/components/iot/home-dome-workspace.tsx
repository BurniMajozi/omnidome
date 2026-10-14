"use client";
import { useEffect, useState } from "react";
import HomeDome from "./home-dome";
import { adminApi } from "@/lib/admin-api";
import { loadCustomers } from "@/lib/crm-api";
import { getSessionSafe } from "@/lib/supabase/client";

const request = async (path: string, init?: RequestInit) => {
  await getSessionSafe();
  return fetch(path.replace("/api/iot/homes", "/api/home-dome"), { ...init, cache: "no-store", signal: AbortSignal.timeout(60000) });
};
export default function HomeDomeWorkspace() {
  const [customers, setCustomers] = useState<{ id: string; label: string }[]>([]);
  const [users, setUsers] = useState<{ id: string; label: string }[]>([]);
  useEffect(() => {
    let alive = true;
    void Promise.allSettled([loadCustomers({ pageSize: 200 }), adminApi.listUsers()]).then(([crm, members]) => {
      if (!alive) return;
      if (crm.status === "fulfilled" && crm.value.state === "ready") setCustomers(crm.value.data.items.map(row => ({ id: row.id, label: `${row.first_name} ${row.last_name} · ${row.account_number || row.email || "Customer"}` })));
      if (members.status === "fulfilled") setUsers(members.value.filter(row => row.is_active !== false).map(row => ({ id: row.id, label: row.full_name || row.name || row.email })));
    });
    return () => { alive = false; };
  }, []);
  return <HomeDome request={request} customers={customers} users={users} theme="dark" />;
}
