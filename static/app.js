/* Tatmaq Books · front-end behaviour */
(function () {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

  /* ------------------------------- toasts */
  $$(".toast").forEach((t, i) => setTimeout(() => {
    t.style.transition = "opacity .4s, transform .4s";
    t.style.opacity = "0"; t.style.transform = "translateY(6px)";
    setTimeout(() => t.remove(), 420);
  }, 4600 + i * 250));

  /* ------------------------------- confirms */
  $$("form[data-confirm]").forEach((f) => f.addEventListener("submit", (e) => {
    if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault();
  }));

  /* ------------------------------- table quick filter */
  $$("input[data-filter]").forEach((inp) => {
    const target = $(inp.getAttribute("data-filter"));
    if (!target) return;
    inp.addEventListener("input", () => {
      const q = inp.value.toLowerCase().trim();
      $$("tbody tr", target).forEach((tr) => {
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
      });
    });
  });

  /* ------------------------------- line editors */
  const fmt = (n) => "$" + (Number(n) || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  function recalc(root) {
    const tbody = $("tbody", root);
    const rate = parseFloat(root.getAttribute("data-tax-rate") || "15") / 100;
    let sub = 0, tax = 0, qtyTotal = 0;
    $$("tr", tbody).forEach((tr) => {
      const qEl2 = tr.querySelector('[name="qty"]');
      const q = parseFloat((qEl2 ? qEl2.value : 0) || 0);
      const pEl = tr.querySelector('[name="price"]') || tr.querySelector('[name="unit_cost"]');
      const p = parseFloat(pEl ? pEl.value : 0) || 0;
      const amt = q * p;
      sub += amt; tax += amt * rate; qtyTotal += q;
      const cell = tr.querySelector(".line-amt");
      if (cell) cell.textContent = amt ? fmt(amt) : "—";
    });
    const set = (sel, v) => { const el = $(sel); if (el) el.textContent = v; };
    set("#t-sub", fmt(sub)); set("#t-tax", fmt(tax)); set("#t-total", fmt(sub + tax));
    const qEl = $("#t-qty"); if (qEl) qEl.textContent = qtyTotal.toLocaleString();
  }

  $$("[data-line-editor]").forEach((root) => {
    const tbody = $("tbody", root);
    const blank = () => {
      const tr = tbody.rows[0].cloneNode(true);
      $$('input', tr).forEach((i) => { if (i.name === "qty") i.value = "1"; else i.value = ""; });
      $$('select', tr).forEach((s) => (s.selectedIndex = 0));
      const cell = tr.querySelector(".line-amt"); if (cell) cell.textContent = "—";
      return tr;
    };
    const add = $("[data-add-line]", root.parentNode) || $("[data-add-line]");
    if (add) add.addEventListener("click", () => {
      tbody.appendChild(blank());
      recalc(root);
    });
    tbody.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-remove-line]");
      if (!btn) return;
      const tr = btn.closest("tr");
      if (tbody.rows.length > 1) tr.remove(); else $$("input", tr).forEach((i) => (i.value = i.name === "qty" ? "1" : ""));
      recalc(root);
    });
    tbody.addEventListener("change", (e) => {
      const sel = e.target.closest("select");
      if (sel) {
        const tr = sel.closest("tr");
        const opt = sel.selectedOptions[0];
        if (opt) {
          // option may carry data-price (sales) or data-cost (purchases)
          const pv = opt.getAttribute("data-price");
          const cv = opt.getAttribute("data-cost");
          const priceInput = tr.querySelector('[name="price"]');
          const costInput = tr.querySelector('[name="unit_cost"]');
          if (priceInput && pv) priceInput.value = pv;
          if (costInput && cv) costInput.value = cv;
          const desc = tr.querySelector('[name="desc"]');
          if (desc && !desc.value && opt.value) {
            desc.value = opt.textContent.trim().replace(/^\d+\s*·\s*/, "");
          }
        }
      }
      recalc(root);
    });
    tbody.addEventListener("input", () => recalc(root));
    recalc(root);
  });

  /* ------------------------------- AI assistant */
  const panel = $("#ai-panel"), fab = $("#ai-fab"), msgs = $("#ai-msgs"),
        form = $("#ai-form"), input = $("#ai-input");
  let DASH = null;

  async function getDash() {
    if (DASH) return DASH;
    try {
      const r = await fetch("/api/dashboard");
      DASH = await r.json();
    } catch (e) { DASH = null; }
    return DASH;
  }

  const money = (n) => "$" + (Number(n) || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const kmoney = (n) => {
    n = Number(n) || 0;
    const a = Math.abs(n);
    if (a >= 1e6) return "$" + (n / 1e6).toFixed(2) + "M";
    if (a >= 1e3) return "$" + (n / 1e3).toFixed(1) + "K";
    return "$" + n.toFixed(0);
  };

  function answer(q, d) {
    const t = q.toLowerCase();
    if (!d) return "I can't reach the ledger right now. Refresh the page and try again — your data is safe.";

    const has = (...k) => k.some((w) => t.includes(w));

    if (has("cash", "runway", "liquid", "bank balance", "money in the bank")) {
      const need = d.runway_months;
      return `💵 <b>Cash position: ${money(d.cash)}</b>\n` +
        `You have about <b>${need.toFixed(1)} months of runway</b> at your current spend rate.\n\n` +
        `Receivables of <b>${money(d.ar_outstanding)}</b> are the fastest lever — collecting just half would add ` +
        `<b>${money(d.ar_outstanding / 2)}</b> to the bank.\n` +
        `Payables of ${money(d.ap_outstanding)} are due, and VAT of ${money(d.vat_payable)} should stay ring-fenced.\n` +
        `<span class="tip">Tip: keep statutory VAT in a separate wallet so it never gets spent as working capital.</span>`;
    }
    if (has("profit", "margin", "doing", "health", "performance", "summary", "overview")) {
      return `📊 <b>Year to date</b>\n` +
        `Revenue: <b>${money(d.revenue_ytd)}</b>\nGross margin: <b>${d.gross_margin_pct}%</b>\n` +
        `Net profit: <b>${money(d.net_profit_ytd)}</b> (${d.net_margin_pct}% net margin)\n\n` +
        `Health score is <b>${d.health_score}/100</b> — ${d.health_score >= 70 ? "this is a strong position." : d.health_score >= 45 ? "the business is stable but has fixable leaks." : "there are urgent issues to address."}\n` +
        `This month you invoiced ${money(d.revenue_this_month)} (${d.revenue_growth_pct >= 0 ? "+" : ""}${d.revenue_growth_pct}% vs last month).\n` +
        `<span class="tip">Want a deep-dive? Ask “biggest expenses” or “who owes me money”.</span>`;
    }
    if (has("owe me", "owed", "receivable", "overdue invoice", "debtor", "collect", "chase")) {
      const a = d.aging;
      const old = a.b3 + a.b4;
      return `🧾 <b>Receivables: ${money(d.ar_outstanding)}</b>\n` +
        `Overdue: <b>${money(d.overdue_value)}</b> across ${d.overdue_invoices} invoice(s).\n\n` +
        `Aging: <b>${kmoney(a.current)}</b> current · <b>${kmoney(a.b1)}</b> 1–30d · ` +
        `<b>${kmoney(a.b2)}</b> 31–60d · <b>${kmoney(old)}</b> over 60 days.\n\n` +
        (old > 0
          ? `${old > d.ar_outstanding * 0.3 ? "⚠️" : "ℹ️"} <b>${kmoney(old)} is over 60 days</b> — that is where collection risk lives. Send statements today and offer a small early-settlement discount on the oldest 3 accounts.`
          : "No old debt — excellent discipline. Keep the 30-day terms and re-confirm due dates on new invoices.")
        + `<span class="tip">Open Sales → Invoices → filter “Overdue” to work the list.</span>`;
    }
    if (has("vat", "zimra", "tax")) {
      return `🏛️ <b>VAT position: ${money(d.vat_payable)} payable</b>\n` +
        `This is output VAT on sales less input VAT on purchases for the current period.\n\n` +
        `ZIMRA expects payment by the <b>25th</b> of the following month. Keep ${money(d.vat_payable)} ring-fenced now, then claim every input VAT invoice you're holding — unclaimed input VAT is the most common cash leak in Zimbabwean SMEs.\n` +
        `<span class="tip">Reports → VAT Return produces the schedule for your returns officer.</span>`;
    }
    if (has("payable", "supplier", "creditor", "do i owe", "bills due")) {
      return `📥 <b>Payables: ${money(d.ap_outstanding)}</b>\n` +
        `Plan payments by due date so supplier terms stay intact. If cash is tight, prioritise suppliers who hold your operations hostage (fuel, power, key stock) and negotiate staged settlement with the rest.\n` +
        `<span class="tip">Ask “cash position” to see if you can clear them comfortably.</span>`;
    }
    if (has("expense", "spend", "cost", "burn", "biggest")) {
      const mx = (d.expense_mix || []).slice(0, 3).map((m) => `<b>${m.name}</b> ${kmoney(m.value)} (${m.pct}%)`).join(", ");
      return `💸 <b>Expenses YTD: ${money(d.expenses_ytd)}</b>\n` +
        `Top drivers: ${mx || "not enough data yet"}.\n\n` +
        (d.expenses_ytd > d.revenue_ytd * 0.85
          ? `⚠️ Expenses are consuming <b>${Math.round(d.expenses_ytd / d.revenue_ytd * 100)}% of revenue</b>. Trim the top two categories by 10% and you keep roughly <b>${kmoney(d.expenses_ytd * 0.02)}</b> extra this year.`
          : `Cost base is manageable at <b>${Math.round(d.expenses_ytd / d.revenue_ytd * 100)}% of revenue</b>. Focus on growing revenue rather than cutting muscle.`)
        + `<span class="tip">Reports → Profit & Loss breaks this down by account.</span>`;
    }
    if (has("customer", "top client", "biggest client", "concentration")) {
      const c = d.top_customers || [];
      if (!c.length) return "No customer sales recorded yet in this fiscal year.";
      const total = c.reduce((s, x) => s + x.value, 0) || 1;
      const lines = c.map((x, i) => `${i + 1}. ${x.name} — <b>${kmoney(x.value)}</b> (${Math.round(x.value / total * 100)}%)`).join("\n");
      return `👥 <b>Top customers this fiscal year</b>\n${lines}\n\n` +
        (c[0] && c[0].value / d.revenue_ytd > 0.3
          ? `⚠️ Your largest account is <b>${Math.round(c[0].value / d.revenue_ytd * 100)}% of revenue</b> — concentration risk. Start a second-lane of prospects this quarter.`
          : `Concentration looks healthy — no single customer dominates the book.`);
    }
    if (has("forecast", "next month", "projection", "predict", "will i")) {
      const m = d.monthly || [];
      const last3 = m.slice(-4, -1);
      const avg = last3.length ? last3.reduce((s, x) => s + x.net, 0) / last3.length : d.net_profit_ytd / 12;
      return `🔮 <b>Next-month outlook</b>\n` +
        `Based on the last 3 months' average net of <b>${money(avg)}</b>, next month projects to roughly ` +
        `<b>${money(avg * 0.9)} – ${money(avg * 1.1)}</b> net profit.\n\n` +
        `Cash forecast: ${money(d.cash)} today + collectible AR ${kmoney(d.ar_outstanding)} − AP ${kmoney(d.ap_outstanding)} = ` +
        `<b>${kmoney(d.cash + d.ar_outstanding - d.ap_outstanding)}</b> potential if everything clears.\n` +
        `<span class="tip">Forecasts are directional — actuals depend on collection speed.</span>`;
    }
    if (has("payroll", "salary", "salaries", "staff", "employee", "paye")) {
      return `👔 <b>People cost</b>\nYou have <b>${d.employees} active employees</b> on the payroll register. Each run computes PAYE on the ZIMRA USD bands (0–100 free, then 20–40%), the 3% AIDS levy and NSSA at 4.5%, then posts the ledger entries automatically.\n` +
        `<span class="tip">Open Operations → Payroll to run this month or view payslips.</span>`;
    }
    if (has("alert", "attention", "focus", "fix", "improve", "advice", "what should")) {
      const a = d.alerts || [];
      const lines = a.length ? a.map((x, i) => `${i + 1}. <b>${x.title}</b>\n   ${x.detail}`).join("\n") : "Nothing urgent flagged — the books are clean.";
      return `🎯 <b>Where I'd focus this week</b>\n${lines}\n\n` +
        `Priority order: protect statutory cash (VAT), collect overdue AR, then reorder low stock before it stalls sales.`;
    }
    if (has("revenue", "sales", "growth", "trend")) {
      const m = (d.monthly || []).slice(-3);
      const dir = m.length >= 2 ? (m[m.length - 1].revenue >= m[m.length - 2].revenue ? "up" : "down") : "flat";
      return `📈 <b>Revenue pulse</b>\nThis month: <b>${money(d.revenue_this_month)}</b> (${d.revenue_growth_pct >= 0 ? "+" : ""}${d.revenue_growth_pct}% vs last month) — trend is ${dir}.\nYear to date: <b>${money(d.revenue_ytd)}</b> at a ${d.gross_margin_pct}% gross margin.\n` +
        `<span class="tip">The dashboard chart shows the full 12-month trajectory.</span>`;
    }
    if (has("industry", "tonne", "production", "pulse", "operations")) {
      return `🏭 <b>${d.company}</b> runs on the <b>${d.industry}</b> template.\n` +
        `Industry KPI — ${d.industry_metric}: <b>${d.industry_value.toLocaleString()}</b> in the last 30 days.\n` +
        `The chart of accounts, billing items and expense categories were built for your sector, and this KPI updates from live invoice lines.\n` +
        `<span class="tip">Switch sectors any time in System → Industry Setup.</span>`;
    }
    if (has("what can you", "help", "capab", "feature", "zoho")) {
      return `I'm your in-app analyst. Try:\n• “How is the business doing?”\n• “What is my cash runway?”\n• “Who owes me money?”\n• “How much VAT do I owe?”\n• “Biggest expenses”\n• “Top customers”\n• “What should I focus on?”\n\nEverything reads live from the double-entry ledger — no exports needed.`;
    }
    return `Here's the headline: revenue YTD <b>${money(d.revenue_ytd)}</b>, net profit <b>${money(d.net_profit_ytd)}</b>, cash <b>${money(d.cash)}</b>, and ${d.overdue_invoices} overdue invoice(s).\n\n` +
      `Ask me about <b>cash</b>, <b>profit</b>, <b>receivables</b>, <b>VAT</b>, <b>expenses</b>, <b>customers</b>, <b>payroll</b> or <b>what to focus on</b>.`;
  }

  function pushMsg(html, who) {
    const div = document.createElement("div");
    div.className = "msg " + (who || "bot");
    div.innerHTML = html;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
  }

  async function respond(q) {
    pushMsg(q.replace(/</g, "&lt;"), "user");
    const typing = pushMsg('<span class="typing"><i></i><i></i><i></i></span>');
    const d = await getDash();
    setTimeout(() => {
      typing.innerHTML = answer(q, d);
      msgs.scrollTop = msgs.scrollHeight;
    }, 420);
  }

  if (fab && panel) {
    fab.addEventListener("click", () => { panel.hidden = false; fab.style.display = "none"; input.focus(); });
    $("#ai-close").addEventListener("click", () => { panel.hidden = true; fab.style.display = ""; });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = input.value.trim();
      if (!q) return;
      input.value = "";
      respond(q);
    });
    msgs.addEventListener("click", (e) => {
      const b = e.target.closest("[data-q]");
      if (b) respond(b.getAttribute("data-q"));
    });
  }

  /* refresh dashboard numbers after data changes when panel opens */
  window.addEventListener("focus", () => { DASH = null; });
})();
