import { fmtMoney } from "@/lib/money"

export const formatCurrency = fmtMoney

export const formatPercent = (value: number) => `${value.toFixed(1)}%`
