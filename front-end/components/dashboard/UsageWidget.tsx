"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { apiMessage } from "@/lib/api";
import { BillingService, type UsageResponse } from "@/lib/client";

/** Shows the user's monthly free-quota usage and prepaid balance. */
export default function UsageWidget() {
  const t = useTranslations("usage");
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    BillingService.getUsage()
      .then((u) => active && setUsage(u))
      .catch((err) => active && setError(apiMessage(err)));
    return () => {
      active = false;
    };
  }, []);

  if (error) return <div className="field-error">{t("loadError")}</div>;
  if (!usage) return null;

  const fmt = (n: number) => n.toLocaleString();

  return (
    <div className="panel">
      <div className="panel-head">
        <div>
          <h3>{t("title")}</h3>
          {usage.free_pages_remaining > 0 && (
            <div className="sub">
              {t("freeUsed", {
                used: usage.pages_used,
                total: usage.pages_used + usage.free_pages_remaining,
              })}
            </div>
          )}
        </div>
        <span className="sc-ico">
          <Sparkles size={18} />
        </span>
      </div>
      <div className="panel-body">
        <div className="val">{t("freeLeft", { count: usage.free_pages_remaining })}</div>
        <div className="sub">
          {t("balance")}: {fmt(usage.balance_vnd)} ₫
        </div>
        <div className="sub">{t("pricePerPage", { price: fmt(usage.price_per_page_vnd) })}</div>
      </div>
    </div>
  );
}
