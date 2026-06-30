"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Check, QrCode, RefreshCw, Wallet } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";
import { apiMessage } from "@/lib/api";
import {
  SepayService,
  TopupService,
  type CreateSepayPaymentResponse,
  type TopupPackage,
  type TopupTransactionPublic,
  type UserBalancePublic,
} from "@/lib/client";
import { formatDate } from "@/lib/files";
import type { DocStatus } from "@/lib/data";
import TopupQrModal from "./TopupQrModal";

const STATUS_PILL: Record<TopupTransactionPublic["status"], DocStatus> = {
  success: "done",
  pending: "proc",
  failed: "fail",
};

// Minimum top-up accepted by the payment gateway (VND).
const MIN_TOPUP = 10_000;

// Loyalty bonus tiers — mirror of backend app/topup/constants.py BONUS_TIERS.
// Used to preview the bonus for custom amounts; the backend remains the source
// of truth and recomputes the bonus when the payment webhook lands.
const BONUS_TIERS: [number, number][] = [
  [10_000_000, 10],
  [5_000_000, 8],
  [2_000_000, 7],
  [1_000_000, 6],
  [500_000, 5],
];

const bonusPercent = (amount: number) =>
  BONUS_TIERS.find(([min]) => amount >= min)?.[1] ?? 0;

const bonusFor = (amount: number) => Math.floor((amount * bonusPercent(amount)) / 100);

export default function BillingView() {
  const t = useTranslations("billing");
  const tc = useTranslations("common");
  const format = useFormatter();

  const [balance, setBalance] = useState<UserBalancePublic | null>(null);
  const [packages, setPackages] = useState<TopupPackage[]>([]);
  const [transactions, setTransactions] = useState<TopupTransactionPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payment, setPayment] = useState<CreateSepayPaymentResponse | null>(null);

  // Selected preset amount, or "custom" when the user types their own value.
  const [selected, setSelected] = useState<number | "custom" | null>(null);
  const [customAmount, setCustomAmount] = useState("");

  const refresh = useCallback(
    (signal?: { active: boolean }) =>
      Promise.all([
        TopupService.getMyBalance(),
        TopupService.getTopupPackages(),
        TopupService.getMyTransactions({ limit: 20 }),
      ])
        .then(([bal, pkgs, txns]) => {
          if (signal && !signal.active) return;
          setBalance(bal);
          setPackages(pkgs.packages);
          setTransactions(txns);
        })
        .catch((err) => (!signal || signal.active) && setError(apiMessage(err))),
    [],
  );

  useEffect(() => {
    const signal = { active: true };
    refresh(signal).finally(() => signal.active && setLoading(false));
    return () => {
      signal.active = false;
    };
  }, [refresh]);

  const vnd = (amount: number) =>
    format.number(amount, { style: "currency", currency: "VND", maximumFractionDigits: 0 });

  // The amount that will actually be charged given the current selection.
  const amount = useMemo<number | null>(() => {
    if (selected === "custom") {
      const n = Number(customAmount.replace(/\D/g, ""));
      return Number.isFinite(n) && n > 0 ? n : null;
    }
    return selected;
  }, [selected, customAmount]);

  const canPay = amount !== null && amount >= MIN_TOPUP;
  const bonus = amount !== null ? bonusFor(amount) : 0;

  const topup = async () => {
    if (!canPay || amount === null) return;
    setPaying(true);
    setError(null);
    try {
      const res = await SepayService.createPayment({ requestBody: { amount } });
      setPayment(res);
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setPaying(false);
    }
  };

  const onPaymentSuccess = () => {
    void refresh();
  };

  return (
    <div className="settings-wrap">
      {error && <div className="field-error">{error}</div>}

      {payment && (
        <TopupQrModal
          txnRef={payment.txn_ref}
          qrUrl={payment.qr_url}
          amount={payment.amount}
          account={payment.account}
          bank={payment.bank}
          content={payment.content}
          onClose={() => setPayment(null)}
          onSuccess={onPaymentSuccess}
        />
      )}

      <div className="set-panel">
        <div className="sp-head">
          <h3>{t("balanceTitle")}</h3>
          <p>{t("balanceSub")}</p>
        </div>
        <div className="set-row">
          <div className="label">
            <div className="t" style={{ fontFamily: "var(--font-mono)", color: "var(--cyan)", fontSize: 22 }}>
              {loading ? tc("loading") : balance ? vnd(balance.balance) : "—"}
            </div>
            <div className="d">
              {balance ? t("balanceUpdated", { date: formatDate(balance.updated_at) }) : ""}
            </div>
          </div>
          <Wallet size={22} style={{ color: "var(--fg-dim)" }} />
        </div>
      </div>

      <div className="set-panel">
        <div className="sp-head">
          <h3>{t("topupTitle")}</h3>
          <p>{t("topupSub")}</p>
        </div>

        {loading ? (
          <div className="set-row">
            <div className="label">
              <div className="d">{tc("loading")}</div>
            </div>
          </div>
        ) : (
          <>
            <div className="topup-grid">
              {packages.map((pkg) => {
                const bonusAmt = pkg.bonus_amount ?? 0;
                const isSel = selected === pkg.amount;
                return (
                  <button
                    type="button"
                    key={pkg.id}
                    className={`topup-card${isSel ? " sel" : ""}${bonusAmt > 0 ? " has-bonus" : ""}`}
                    onClick={() => setSelected(pkg.amount)}
                    aria-pressed={isSel}
                  >
                    <div className="tc-top">
                      {(pkg.bonus_percent ?? 0) > 0 && (
                        <span className="topup-bonus">
                          {t("bonusBadge", { percent: pkg.bonus_percent })}
                        </span>
                      )}
                      <span className="tc-check">{isSel && <Check size={13} strokeWidth={3} />}</span>
                    </div>
                    <div className="amt">{vnd(pkg.amount)}</div>
                    <div className={bonusAmt > 0 ? "lbl bonus" : "lbl"}>
                      {bonusAmt > 0
                        ? t("bonusGet", { amount: vnd(pkg.amount + bonusAmt) })
                        : pkg.label}
                    </div>
                  </button>
                );
              })}

              <button
                type="button"
                className={`topup-card topup-card-custom${selected === "custom" ? " sel" : ""}`}
                onClick={() => setSelected("custom")}
                aria-pressed={selected === "custom"}
              >
                <div className="tc-top">
                  <span className="tc-check">
                    {selected === "custom" && <Check size={13} strokeWidth={3} />}
                  </span>
                </div>
                <div className="amt">{t("customAmount")}</div>
                <div className="lbl">{t("customHint")}</div>
              </button>
            </div>

            {selected === "custom" && (
              <div className="topup-custom field">
                <label htmlFor="topup-custom-input">{t("customLabel")}</label>
                <input
                  id="topup-custom-input"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder={t("customPlaceholder")}
                  value={customAmount ? vnd(Number(customAmount.replace(/\D/g, "")) || 0) : ""}
                  onChange={(e) => setCustomAmount(e.target.value.replace(/\D/g, ""))}
                />
              </div>
            )}

            <div className="topup-foot">
              <div className="d" style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-dim)" }}>
                {amount === null ? (
                  t("selectPrompt")
                ) : !canPay ? (
                  t("minHint", { min: vnd(MIN_TOPUP) })
                ) : bonus > 0 ? (
                  <>
                    {t("payHint", { amount: vnd(amount) })}{" "}
                    <span style={{ color: "var(--cyan)" }}>
                      {t("bonusReceive", { total: vnd(amount + bonus), bonus: vnd(bonus) })}
                    </span>
                  </>
                ) : (
                  t("payHint", { amount: vnd(amount) })
                )}
              </div>
              <button
                className="btn btn-primary"
                onClick={() => void topup()}
                disabled={!canPay || paying}
              >
                {paying ? (
                  <>
                    <RefreshCw size={15} className="spin" /> {tc("loading")}
                  </>
                ) : (
                  <>
                    <QrCode size={15} /> {t("generateQr")}
                  </>
                )}
              </button>
            </div>

            {packages.length === 0 && (
              <div className="set-row">
                <div className="label">
                  <div className="d">{t("noPackages")}</div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <div className="set-panel">
        <div className="sp-head">
          <h3>{t("transactionsTitle")}</h3>
          <p>{t("transactionsSub")}</p>
        </div>
        <table className="tbl">
          <thead>
            <tr>
              <th>{t("colRef")}</th>
              <th>{t("colDate")}</th>
              <th>{t("colType")}</th>
              <th>{t("colAmount")}</th>
              <th>{t("colStatus")}</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr className="empty-row">
                <td colSpan={5}>{tc("loading")}</td>
              </tr>
            )}
            {!loading && transactions.length === 0 && (
              <tr className="empty-row">
                <td colSpan={5}>{t("noTransactions")}</td>
              </tr>
            )}
            {transactions.map((txn) => (
              <tr key={txn.id}>
                <td className="mono-cell">{txn.txn_ref ?? txn.id.slice(0, 8)}</td>
                <td className="mono-cell">{formatDate(txn.created_at)}</td>
                <td className="mono-cell">
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                    {txn.type === "credit" ? (
                      <ArrowUpRight size={13} style={{ color: "var(--ok)" }} />
                    ) : (
                      <ArrowDownRight size={13} style={{ color: "var(--fg-dim)" }} />
                    )}
                    {txn.type === "credit" ? t("typeCredit") : t("typeDebit")}
                  </span>
                </td>
                <td className="mono-cell">{vnd(txn.amount)}</td>
                <td>
                  <span className={`pill ${STATUS_PILL[txn.status]}`}>
                    <span className="dot" />
                    {t(`status_${txn.status}`)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
