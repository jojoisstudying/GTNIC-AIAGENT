import { useMemo, useState } from 'react';
import {
  Building2,
  CheckCircle2,
  Circle,
  ClipboardList,
  Clock,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Sliders,
  Target,
  Trash2,
} from 'lucide-react';
import { Alert, Badge, Button, Card, CardHeader, EmptyState, Field, Input, PageHeader, ProgressBar, Textarea } from '../components/ui';

const toLines = (value) => (Array.isArray(value) ? value.join('\n') : '');
const fromLines = (value) =>
  String(value || '')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);

export default function Enterprise({ profile, setProfile, onSave, saving, loading, error, onReload }) {
  const [pillarsText, setPillarsText] = useState(() => toLines(profile?.content_pillars));
  const [rulesText, setRulesText] = useState(() => toLines(profile?.brand_rules));
  const [goalsText, setGoalsText] = useState(() => toLines(profile?.business_goals));
  const [initializedFor, setInitializedFor] = useState(profile?.id ?? null);

  // Sinkronkan form ketika profil pertama kali dimuat
  if (profile && initializedFor !== profile.id) {
    setInitializedFor(profile.id);
    setPillarsText(toLines(profile.content_pillars));
    setRulesText(toLines(profile.brand_rules));
    setGoalsText(toLines(profile.business_goals));
  }

  const checks = useMemo(
    () => [
      { label: 'Nama perusahaan', done: Boolean(profile?.company_name?.trim()) },
      { label: 'Bidang usaha', done: Boolean(profile?.industry?.trim()) },
      { label: 'Deskripsi usaha', done: Boolean(profile?.description?.trim()) },
      { label: 'Tone of voice', done: Boolean(profile?.tone?.trim()) },
      { label: 'Produk & layanan', done: (profile?.products_services || []).length > 0 },
      { label: 'Pilar konten', done: (profile?.content_pillars || []).length > 0 },
      { label: 'Aturan brand', done: (profile?.brand_rules || []).length > 0 },
      { label: 'Target audiens', done: Boolean(profile?.target_audience?.primary_segment) },
      { label: 'Tujuan bisnis', done: (profile?.business_goals || []).length > 0 },
    ],
    [profile]
  );

  if (loading && !profile) {
    return (
      <div className="space-y-4">
        <PageHeader title="Profil enterprise" description="Memuat konteks usaha…" />
        <div className="card h-48 animate-pulse" aria-hidden="true" />
      </div>
    );
  }

  if (error && !profile) {
    return (
      <div className="space-y-4">
        <PageHeader title="Profil enterprise" description="Konteks resmi usaha untuk AI." />
        <EmptyState
          icon={Building2}
          title="Profil tidak bisa dimuat"
          description={error}
          action={<Button icon={RefreshCw} onClick={onReload}>Coba lagi</Button>}
        />
      </div>
    );
  }

  if (!profile) return null;

  const complete = checks.filter((check) => check.done).length;
  const score = profile.completeness_score ?? Math.round((complete / checks.length) * 100);

  const submit = (event) => {
    event.preventDefault();
    onSave({
      ...profile,
      content_pillars: fromLines(pillarsText),
      brand_rules: fromLines(rulesText),
      business_goals: fromLines(goalsText),
    });
  };

  const addProduct = () => {
    const list = [...(profile.products_services || [])];
    list.push({ name: '', desc: '', value_prop: '' });
    setProfile({ ...profile, products_services: list });
  };

  const updateProduct = (index, patch) => {
    const list = [...(profile.products_services || [])];
    list[index] = { ...list[index], ...patch };
    setProfile({ ...profile, products_services: list });
  };

  const removeProduct = (index) => {
    const list = (profile.products_services || []).filter((_, i) => i !== index);
    setProfile({ ...profile, products_services: list });
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Profil enterprise"
        description="AI memakai profil ini sebagai sumber kebenaran saat meriset dan menulis konten. Isi dengan bahasa yang jelas dan jujur."
        actions={
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={onReload} loading={loading}>
            Muat ulang
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title="Informasi utama" description="Perubahan disimpan sebagai versi baru profil." icon={Building2} />
          <form onSubmit={submit} className="space-y-4 p-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Nama perusahaan" htmlFor="ent-company" required>
                <Input
                  id="ent-company"
                  value={profile.company_name || ''}
                  onChange={(event) => setProfile({ ...profile, company_name: event.target.value })}
                  required
                  maxLength={160}
                />
              </Field>
              <Field label="Bidang usaha" htmlFor="ent-industry" required>
                <Input
                  id="ent-industry"
                  value={profile.industry || ''}
                  onChange={(event) => setProfile({ ...profile, industry: event.target.value })}
                  required
                  maxLength={160}
                />
              </Field>
            </div>

            <Field
              label="Deskripsi usaha"
              htmlFor="ent-description"
              hint="Jelaskan apa yang Anda jual, untuk siapa, dan apa yang membuatnya berbeda."
            >
              <Textarea
                id="ent-description"
                rows={4}
                value={profile.description || ''}
                onChange={(event) => setProfile({ ...profile, description: event.target.value })}
                maxLength={1200}
              />
            </Field>

            <Field label="Tone of voice" htmlFor="ent-tone" hint="Contoh: ramah, santai, bahasa sehari-hari, tetap sopan.">
              <Input
                id="ent-tone"
                value={profile.tone || ''}
                onChange={(event) => setProfile({ ...profile, tone: event.target.value })}
                maxLength={200}
              />
            </Field>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Pilar konten" htmlFor="ent-pillars" hint="Satu pilar per baris. Pilar menjaga variasi topik.">
                <Textarea
                  id="ent-pillars"
                  rows={4}
                  value={pillarsText}
                  onChange={(event) => setPillarsText(event.target.value)}
                  placeholder={'Tips praktis\nStudi kasus\nPromo'}
                />
              </Field>
              <Field label="Aturan brand" htmlFor="ent-rules" hint="Satu aturan per baris. AI wajib mematuhi aturan ini.">
                <Textarea
                  id="ent-rules"
                  rows={4}
                  value={rulesText}
                  onChange={(event) => setRulesText(event.target.value)}
                  placeholder={'Jangan pakai klaim berlebihan\nSelalu sebutkan sumber data'}
                />
              </Field>
            </div>

            <div className="space-y-4 border-t border-line pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-ink">Katalog Produk & Layanan</h3>
                  <p className="text-xs text-ink-muted">AI akan mempromosikan atau mengaitkan konten dengan produk ini.</p>
                </div>
                <Button size="xs" variant="secondary" icon={Plus} onClick={addProduct}>
                  Tambah Produk
                </Button>
              </div>

              {(profile.products_services || []).length === 0 ? (
                <p className="rounded-xl border border-dashed border-line p-4 text-center text-xs text-ink-muted">
                  Belum ada produk/layanan yang ditambahkan. Klik &quot;Tambah Produk&quot; untuk memasukkan produk bisnis Anda.
                </p>
              ) : (
                <div className="space-y-3">
                  {(profile.products_services || []).map((prod, idx) => (
                    <div key={idx} className="relative rounded-xl border border-line bg-canvas p-3.5 space-y-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <Input
                          placeholder="Nama Produk / Layanan (misal: Enterprise AI Automation)"
                          value={prod.name || ''}
                          className="font-medium text-sm"
                          onChange={(e) => updateProduct(idx, { name: e.target.value })}
                        />
                        <button
                          type="button"
                          onClick={() => removeProduct(idx)}
                          className="text-ink-muted hover:text-danger-600 p-1"
                          title="Hapus produk"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                      <Input
                        placeholder="Deskripsi singkat produk"
                        value={prod.desc || ''}
                        className="text-xs"
                        onChange={(e) => updateProduct(idx, { desc: e.target.value })}
                      />
                      <Input
                        placeholder="Nilai jual / Value proposition (misal: Hemat biaya operasional 40%)"
                        value={prod.value_prop || ''}
                        className="text-xs"
                        onChange={(e) => updateProduct(idx, { value_prop: e.target.value })}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 border-t border-line pt-4">
              <Field
                label="Target Audiens (Segmen Utama)"
                htmlFor="ent-audience"
                hint="Siapa audiens yang Anda targetkan?"
              >
                <Input
                  id="ent-audience"
                  value={profile.target_audience?.primary_segment || ''}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      target_audience: {
                        ...(profile.target_audience || {}),
                        primary_segment: e.target.value,
                      },
                    })
                  }
                  placeholder="Contoh: Pemilik UMKM, Manajer Operasional, CTO"
                />
              </Field>

              <Field
                label="Masalah Utama Audiens (Pain Points)"
                htmlFor="ent-pain-points"
                hint="Pisahkan dengan koma"
              >
                <Input
                  id="ent-pain-points"
                  value={(profile.target_audience?.pain_points || []).join(', ')}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      target_audience: {
                        ...(profile.target_audience || {}),
                        pain_points: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                      },
                    })
                  }
                  placeholder="Contoh: Biaya operasional tinggi, Waktu terbatas"
                />
              </Field>
            </div>

            <Field
              label="Tujuan Bisnis (Business Goals)"
              htmlFor="ent-goals"
              hint="Satu tujuan per baris. Contoh: Membangun reputasi brand, Lead generation untuk konsultasi."
            >
              <Textarea
                id="ent-goals"
                rows={3}
                value={goalsText}
                onChange={(e) => setGoalsText(e.target.value)}
                placeholder={'Brand awareness\nLead generation konsultasi\nEdukasi pasar'}
              />
            </Field>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 border-t border-line pt-4">
              <Field
                label="Mode Publikasi Otomatis"
                hint="Tentukan apakah AI langsung menjadwalkan konten setelah QC lulus atau masuk antrean review"
              >
                <select
                  className="input"
                  value={profile.publishing_mode || 'autopilot'}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      publishing_mode: e.target.value,
                    })
                  }
                >
                  <option value="autopilot">Autopilot (Otomatis generate, QC, jadwalkan, & publish)</option>
                  <option value="review">Review Mode (Hanya buat draf & tunggu persetujuan)</option>
                </select>
              </Field>

              <Field
                label="Mode Alur Persetujuan (Approval Workflow)"
                hint="Bagaimana konten divalidasi sebelum diposting"
              >
                <select
                  className="input"
                  value={profile.approval_workflow?.default_mode || 'autonomous_routine'}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      approval_workflow: {
                        ...(profile.approval_workflow || {}),
                        default_mode: e.target.value,
                        autonomy_mode: e.target.value,
                      },
                    })
                  }
                >
                  <option value="autonomous_routine">Otonom Rutin (Review opsional)</option>
                  <option value="manual_review">Wajib Persetujuan Manusia</option>
                  <option value="strict_governance">Tata Kelola Ketat (Multi-stage review)</option>
                </select>
              </Field>

              <Field
                label="Target Frekuensi Mingguan"
                hint="Jumlah postingan yang ditargetkan per minggu"
              >
                <input
                  type="number"
                  min="1"
                  max="14"
                  className="input"
                  value={profile.operating_preferences?.target_weekly_posts || 5}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      operating_preferences: {
                        ...(profile.operating_preferences || {}),
                        target_weekly_posts: Number(e.target.value) || 5,
                      },
                    })
                  }
                />
              </Field>
            </div>

            <Alert tone="info">
              Profil ini juga tersinkron ke konfigurasi brand. Menyimpan akan membuat versi baru agar perubahan bisa
              dilacak.
            </Alert>

            <div className="flex justify-end border-t border-line pt-4">
              <Button type="submit" icon={Save} loading={saving} className="w-full sm:w-auto">
                Simpan profil
              </Button>
            </div>
          </form>
        </Card>

        <div className="space-y-4">
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-ink">Kelengkapan profil</h2>
              <Badge tone={score >= 80 ? 'success' : score >= 50 ? 'warning' : 'neutral'}>{score}%</Badge>
            </div>
            <ProgressBar value={score} className="mt-2" tone={score >= 80 ? 'success' : score >= 50 ? 'warning' : 'brand'} />
            <ul className="mt-3 space-y-1.5">
              {checks.map((check) => (
                <li key={check.label} className="flex items-center gap-2 text-xs">
                  {check.done ? (
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success-500" aria-hidden="true" />
                  ) : (
                    <Circle className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden="true" />
                  )}
                  <span className={check.done ? 'text-ink-muted' : 'text-ink'}>{check.label}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Produk & layanan" icon={ClipboardList} />
            <div className="space-y-2 p-4">
              {(profile.products_services || []).length === 0 ? (
                <p className="text-xs text-ink-muted">Belum ada produk yang tercatat di profil.</p>
              ) : (
                (profile.products_services || []).map((product, index) => (
                  <div key={index} className="rounded-xl border border-line bg-canvas p-3">
                    <p className="text-sm font-medium text-ink">{product.name}</p>
                    {product.desc && <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{product.desc}</p>}
                    {product.value_prop && (
                      <p className="mt-1 text-[11px] font-medium text-brand-700">Nilai jual: {product.value_prop}</p>
                    )}
                  </div>
                ))
              )}
              <p className="text-[11px] leading-relaxed text-ink-subtle">
                Produk dikelola di konfigurasi server. Hubungi admin sistem untuk menambah atau mengubahnya.
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader title="Audiens & tujuan" icon={Target} />
            <div className="space-y-2 p-4 text-xs">
              <div className="rounded-xl bg-canvas p-3">
                <p className="font-medium text-ink">Segmen utama</p>
                <p className="mt-0.5 text-ink-muted">{profile.target_audience?.primary_segment || 'Belum diisi'}</p>
                {profile.target_audience?.pain_points?.length > 0 && (
                  <p className="mt-1 leading-relaxed text-ink-muted">
                    Masalah utama: {profile.target_audience.pain_points.join(', ')}
                  </p>
                )}
              </div>
              {profile.business_goals?.length > 0 ? (
                <ul className="list-inside list-disc space-y-1 text-ink-muted">
                  {profile.business_goals.map((goal, index) => <li key={index}>{goal}</li>)}
                </ul>
              ) : (
                <p className="text-ink-muted">Tujuan bisnis belum diisi.</p>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Kepatuhan & kontak" icon={ShieldCheck} />
            <div className="space-y-1.5 p-4 text-xs text-ink-muted">
              <p>Alur persetujuan: <span className="font-medium text-ink">{profile.approval_workflow?.default_mode || 'manual_review'}</span></p>
              <p>Website: <span className="font-medium text-ink">{profile.contact_info?.website || '-'}</span></p>
              <p>Email: <span className="font-medium text-ink">{profile.contact_info?.email || '-'}</span></p>
              {profile.updated_at && <p className="text-[11px] text-ink-subtle">Terakhir diperbarui {profile.updated_at.slice(0, 10)}</p>}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
