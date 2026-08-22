"use client";

import { useEffect, useRef, useState } from "react";
import { DEMO_ADDRESSES } from "@/lib/fixtures";
import { parseAddress, validateAddress } from "@/lib/api";
import type { AddressComponent, AddressField, ComponentState, ReviewResult, ReviewStatus } from "@/lib/types";
import {
  AlertIcon, ArrowIcon, CheckIcon, ChevronIcon, CloseIcon, CopyIcon, EditIcon,
  PinIcon, RefreshIcon, ShieldIcon, SparkIcon, TrashIcon,
} from "./icons";

const STATUS: Record<ReviewStatus, { title: string; eyebrow: string; description: string }> = {
  SIAP_DIPROSES: {
    title: "Siap diproses",
    eyebrow: "Alamat lolos pemeriksaan",
    description: "Semua komponen utama cocok dan alamat final aman digunakan untuk fulfillment.",
  },
  PERLU_KONFIRMASI: {
    title: "Perlu konfirmasi",
    eyebrow: "Ada 1 hal yang perlu diperiksa",
    description: "Kami menemukan perbedaan pada data referensi. Pilihan Anda tidak akan diterapkan otomatis.",
  },
  TIDAK_VALID: {
    title: "Belum dapat diproses",
    eyebrow: "Informasi alamat belum cukup",
    description: "Lengkapi komponen yang ditandai agar alamat dapat diperiksa kembali.",
  },
};

const STATE_LABEL: Record<ComponentState, string> = {
  original: "Terdeteksi", suggested: "Saran", confirmed: "Dikonfirmasi", rejected: "Ditolak", "user-edited": "Diedit",
};

function Header() {
  const healthAvailable = process.env.NEXT_PUBLIC_HEALTH_AVAILABLE === "true";
  return (
    <header className="site-header">
      <a href="#main" className="brand" aria-label="ALAMATIN, kembali ke awal">
        <span className="brand-mark"><PinIcon size={21} /></span>
        <span>ALAMATIN</span>
      </a>
      <div className="header-meta">
        <span className="privacy-note"><ShieldIcon size={15} /> Data tidak disimpan</span>
        {healthAvailable && <span className="health"><i /> Sistem beroperasi</span>}
      </div>
    </header>
  );
}

function EmptyResult() {
  return (
    <section className="result-shell empty-result" aria-label="Belum ada hasil">
      <div className="empty-illustration">
        <span className="radar-ring ring-one" /><span className="radar-ring ring-two" />
        <span className="map-route" /><span className="empty-pin"><PinIcon size={31} /></span>
        <i className="point point-a"/><i className="point point-b"/><i className="point point-c"/>
      </div>
      <span className="overline">RUANG REVIEW</span>
      <h2>Detail alamat akan tampil di sini</h2>
      <p>Masukkan alamat di panel kiri. Kami akan memetakan komponennya dan menunjukkan apa yang perlu diperhatikan.</p>
      <div className="empty-features">
        <span><CheckIcon size={15}/> Komponen terstruktur</span>
        <span><CheckIcon size={15}/> Validasi wilayah</span>
        <span><CheckIcon size={15}/> Siap salin</span>
      </div>
    </section>
  );
}

function LoadingResult() {
  return (
    <section className="result-shell loading-result" aria-label="Sedang memeriksa alamat">
      <div className="scan-animation"><PinIcon size={28}/><span /></div>
      <h2>Sedang membaca alamat…</h2>
      <p>Memisahkan komponen dan mencocokkan data wilayah.</p>
      <div className="skeleton wide"/><div className="skeleton"/><div className="skeleton"/><div className="skeleton short"/>
    </section>
  );
}

function StatusBanner({ result, dirty }: { result: ReviewResult; dirty: boolean }) {
  const copy = STATUS[result.status];
  const Icon = result.status === "SIAP_DIPROSES" ? CheckIcon : result.status === "PERLU_KONFIRMASI" ? AlertIcon : CloseIcon;
  return (
    <section className={`status-banner status-${result.status.toLowerCase()} ${dirty ? "is-dirty" : ""}`} aria-live="polite">
      <span className="status-icon"><Icon size={24}/></span>
      <div>
        <span className="status-eyebrow">{dirty ? "HASIL PERLU DIPERBARUI" : copy.eyebrow}</span>
        <h2>{dirty ? "Perubahan belum divalidasi" : copy.title}</h2>
        <p>{dirty ? "Jalankan validasi ulang untuk memastikan hasil terbaru aman digunakan." : copy.description}</p>
      </div>
      <span className="status-code">{dirty ? "DRAF" : result.status.replaceAll("_", " ")}</span>
    </section>
  );
}

function ComponentsPanel({
  components, redactedInput, onEdit,
}: {
  components: AddressComponent[];
  redactedInput: string;
  onEdit: (field: AddressComponent["field"], value: string) => void;
}) {
  const [editing, setEditing] = useState<AddressComponent["field"] | null>(null);
  return (
    <section className="panel component-panel">
      <div className="panel-heading">
        <div><span className="step-number">01</span><div><h3>Komponen alamat</h3><p>Nilai yang berhasil dikenali</p></div></div>
        <span className="field-count">{components.filter((item) => item.value).length}/10 terisi</span>
      </div>
      {/* The redacted text comes from the API's PII section. It is shown instead
          of the raw input, and instead of a line rebuilt from parsed components:
          a rebuilt line silently drops any PII the parser did not classify, such
          as a recipient name or phone number, so it is not safe to display. */}
      <div className="redacted-strip" aria-label="Input setelah redaksi PII">
        <span>INPUT TEREDUKSI</span>
        <p className="redacted-text">{redactedInput}</p>
      </div>
      <div className="recognized-strip" aria-label="Token alamat yang dikenali">
        <span>KOMPONEN DIKENALI</span>
        <p>{components.filter((item) => item.value).map((item) => (
          <mark className={`token-${item.field.toLowerCase()}`} key={item.field} title={item.label}>{item.value}</mark>
        ))}</p>
      </div>
      <div className="component-list">
        {components.map((item) => (
          <div className={`component-row state-${item.state} ${!item.value ? "is-empty" : ""}`} key={item.field}>
            <div className="component-name"><span className="field-dot"/><span>{item.label}</span></div>
            <div className="component-value">
              {editing === item.field ? (
                <input
                  autoFocus
                  value={item.value}
                  aria-label={`Edit ${item.label}`}
                  onChange={(event) => onEdit(item.field, event.target.value)}
                  onBlur={() => setEditing(null)}
                  onKeyDown={(event) => event.key === "Enter" && setEditing(null)}
                />
              ) : <strong>{item.value || "Belum ditemukan"}</strong>}
              {item.previousValue && <small>Sebelumnya: {item.previousValue}</small>}
            </div>
            <div className="component-source">
              {item.value && <><span className={`state-badge badge-${item.state}`}>{STATE_LABEL[item.state]}</span><small>{item.source} {item.modelScore ? `· model_score ${Math.round(item.modelScore * 100)}%` : ""}</small></>}
            </div>
            <button className="edit-button" onClick={() => setEditing(item.field)} aria-label={`Edit ${item.label}`}><EditIcon size={16}/></button>
          </div>
        ))}
      </div>
    </section>
  );
}

function IssuesPanel({
  result, onResolve,
}: {
  result: ReviewResult;
  onResolve: (field: AddressField, choice: "confirm" | "reject") => void;
}) {
  if (!result.issues.length) return (
    <section className="panel clean-panel">
      <span className="clean-icon"><ShieldIcon size={23}/></span>
      <div><h3>Tidak ada masalah ditemukan</h3><p>Hirarki wilayah dan kode pos konsisten dengan referensi.</p></div>
    </section>
  );

  return (
    <section className="panel issues-panel">
      <div className="panel-heading">
        <div><span className="step-number">02</span><div><h3>Perlu perhatian</h3><p>{result.issues.length} temuan untuk ditindaklanjuti</p></div></div>
      </div>
      {result.issues.map((issue) => (
        <article className={`issue-card severity-${issue.severity}`} key={issue.id}>
          <div className="issue-topline"><span>{issue.severity === "high" ? "PRIORITAS TINGGI" : issue.severity.toUpperCase()}</span><code>{issue.reasonCode}</code></div>
          <h4>{issue.title}</h4>
          <p>{issue.message}</p>
          <div className="affected-fields">{issue.affectedFields.map((field) => <span key={field}>{field.replace("KOTA_KABUPATEN", "KOTA/KAB.")}</span>)}</div>
          {issue.question && <div className="clarification"><span className="question-mark">?</span><strong>{issue.question}</strong></div>}
          {/* Actions are driven by whichever affected field actually carries an
              unresolved suggestion, not by a specific reason code. The previous
              version was gated on a reason code the frozen contract does not
              define, so it never rendered against real API data. */}
          {issue.affectedFields
            .map((field) => result.components.find((item) => item.field === field))
            .filter((item): item is AddressComponent =>
              Boolean(item?.suggestion) && item?.state === "suggested")
            .map((item) => (
              <div className="issue-actions" key={item.field}>
                <button
                  className="primary small"
                  onClick={() => onResolve(item.field, "confirm")}
                  aria-label={`Gunakan ${item.suggestion} untuk ${item.label}`}
                >
                  <CheckIcon size={16}/> Gunakan {item.suggestion}
                </button>
                <button
                  className="secondary small"
                  onClick={() => onResolve(item.field, "reject")}
                  aria-label={item.value ? `Pertahankan ${item.value} untuk ${item.label}` : `Tolak saran untuk ${item.label}`}
                >
                  <CloseIcon size={16}/> {item.value ? `Pertahankan ${item.value}` : "Tolak saran"}
                </button>
              </div>
            ))}
        </article>
      ))}
    </section>
  );
}

function OutputPanel({ result, dirty }: { result: ReviewResult; dirty: boolean }) {
  const [copied, setCopied] = useState(false);
  const enabled = result.isFinal && !dirty;
  const copyResult = async () => {
    try {
      await navigator.clipboard.writeText(result.normalizedAddress);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch { setCopied(false); }
  };
  return (
    <section className={`panel output-panel ${enabled ? "is-final" : ""}`}>
      <div className="panel-heading">
        <div><span className="step-number">03</span><div><h3>Alamat ternormalisasi</h3><p>{enabled ? "Final · lolos quality gate" : "Pratinjau · belum final"}</p></div></div>
        <span className={`final-badge ${enabled ? "final" : "draft"}`}>{enabled ? <><CheckIcon size={14}/> FINAL</> : "BELUM FINAL"}</span>
      </div>
      <div className="output-box"><p>{result.normalizedAddress || "Alamat belum dapat disusun."}</p></div>
      <button className="copy-button" disabled={!enabled} onClick={copyResult}>
        {copied ? <><CheckIcon size={18}/> Berhasil disalin</> : <><CopyIcon size={18}/> Salin alamat final</>}
      </button>
      {!enabled && <p className="copy-hint"><ShieldIcon size={14}/> Tombol aktif setelah alamat lolos validasi.</p>}
    </section>
  );
}

export function AddressReview() {
  const [rawAddress, setRawAddress] = useState("");
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const runParse = async () => {
    if (!rawAddress.trim()) { setError("Masukkan alamat terlebih dahulu."); return; }
    if (rawAddress.length > 500) { setError("Alamat terlalu panjang. Maksimum 500 karakter."); return; }
    const requestId = ++requestRef.current;
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true); setError(""); setDirty(false);
    try {
      const next = await parseAddress(rawAddress, abortRef.current.signal);
      if (requestId === requestRef.current) setResult(next);
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(reason instanceof Error && reason.message === "dependency"
        ? "Layanan referensi sedang tidak tersedia. Coba lagi beberapa saat."
        : "Alamat belum berhasil diperiksa. Periksa koneksi lalu coba lagi.");
    } finally { if (requestId === requestRef.current) setLoading(false); }
  };

  const useDemo = (value: string) => { setRawAddress(value); setResult(null); setError(""); setDirty(false); };

  const editComponent = (field: AddressComponent["field"], value: string) => {
    setResult((current) => current && ({
      ...current,
      components: current.components.map((item) => item.field === field ? {
        ...item, previousValue: item.previousValue ?? item.value, value, state: "user-edited", source: "user",
      } : item),
    }));
    setDirty(true);
  };

  const resolveIssue = (field: AddressField, choice: "confirm" | "reject") => {
    setResult((current) => current && ({
      ...current,
      components: current.components.map((item) => item.field === field ? {
        ...item,
        previousValue: item.value,
        value: choice === "confirm" ? (item.suggestion ?? item.value) : item.value,
        state: choice === "confirm" ? "confirmed" : "rejected",
        source: "user",
      } : item),
    }));
    setDirty(true);
  };

  const revalidate = async () => {
    if (!result) return;
    setLoading(true); setError("");
    try { setResult(await validateAddress(result, result.components)); setDirty(false); }
    catch { setError("Validasi ulang gagal. Perubahan Anda masih tersimpan di halaman ini."); }
    finally { setLoading(false); }
  };

  const clear = () => { abortRef.current?.abort(); setRawAddress(""); setResult(null); setDirty(false); setError(""); setLoading(false); };

  return (
    <div className="app-shell">
      <Header />
      <main id="main">
        <section className="intro">
          <div>
            <span className="intro-kicker"><SparkIcon size={14}/> ADDRESS INTELLIGENCE</span>
            <h1>Alamat rapi.<br/><em>Pengiriman lebih pasti.</em></h1>
          </div>
          <p>Periksa satu alamat Indonesia sebelum membuat resi. Kenali komponennya, selesaikan keraguan, lalu salin hasil final.</p>
        </section>

        <div className="workspace">
          <aside className="input-card">
            <div className="input-card-top">
              <span className="card-index">01</span>
              <div><h2>Masukkan alamat</h2><p>Tempel alamat persis seperti yang Anda terima.</p></div>
            </div>
            <label htmlFor="raw-address">Alamat mentah</label>
            <div className={`textarea-wrap ${error ? "has-error" : ""}`}>
              <textarea
                id="raw-address"
                value={rawAddress}
                onChange={(event) => { setRawAddress(event.target.value); setError(""); }}
                placeholder="Contoh: Jl. Braga No. 99, Braga, Sumur Bandung, Kota Bandung, Jawa Barat 40111"
                maxLength={501}
                aria-describedby={error ? "address-help address-error" : "address-help"}
              />
              <span className="char-count">{rawAddress.length}<i>/500</i></span>
            </div>
            <div id="address-help" className="privacy-line"><ShieldIcon size={14}/> Alamat hanya diproses untuk sesi ini</div>
            {error && <p className="input-error" id="address-error" role="alert"><AlertIcon size={15}/>{error}</p>}
            <div className="input-actions">
              <button className="clear-button" onClick={clear} disabled={!rawAddress && !result}><TrashIcon size={17}/> Bersihkan</button>
              <button className="primary inspect-button" onClick={runParse} disabled={!rawAddress.trim() || loading}>
                {loading ? <><span className="spinner"/> Memeriksa…</> : <>Periksa alamat <ArrowIcon size={18}/></>}
              </button>
            </div>
            <div className="demo-block">
              <span>Coba contoh</span>
              <div className="demo-options">
                <button onClick={() => useDemo(DEMO_ADDRESSES.ready)}><i className="demo-dot ready"/> Alamat lengkap</button>
                <button onClick={() => useDemo(DEMO_ADDRESSES.confirmation)}><i className="demo-dot warning"/> Perlu konfirmasi</button>
                <button onClick={() => useDemo(DEMO_ADDRESSES.invalid)}><i className="demo-dot invalid"/> Tidak lengkap</button>
              </div>
            </div>
            <div className="privacy-card"><ShieldIcon size={18}/><div><strong>Privasi terjaga</strong><p>Tidak disimpan ke riwayat, URL, atau penyimpanan browser.</p></div></div>
          </aside>

          <div className="results-column">
            {loading && !result ? <LoadingResult/> : !result ? <EmptyResult/> : (
              <>
                <StatusBanner result={result} dirty={dirty}/>
                {dirty && <button className="revalidate-bar" onClick={revalidate} disabled={loading}><RefreshIcon size={17}/>{loading ? "Memvalidasi perubahan…" : "Validasi ulang perubahan"}<ArrowIcon size={17}/></button>}
                <ComponentsPanel components={result.components} redactedInput={result.redactedInput} onEdit={editComponent}/>
                <IssuesPanel result={result} onResolve={resolveIssue}/>
                <OutputPanel result={result} dirty={dirty}/>
                <details className="technical-details">
                  <summary><ChevronIcon size={16}/> Detail teknis</summary>
                  <div>{Object.entries(result.versions).map(([key, value]) => <p key={key}><span>{key}</span><code>{value}</code></p>)}</div>
                </details>
              </>
            )}
          </div>
        </div>
      </main>
      <footer><span>ALAMATIN <i>•</i> MVP REVIEW</span><p>Dibuat untuk operasi fulfillment Indonesia.</p></footer>
    </div>
  );
}
