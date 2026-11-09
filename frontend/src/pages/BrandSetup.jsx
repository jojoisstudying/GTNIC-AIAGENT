import { useRef, useState } from 'react';
import {
  Check,
  Image as ImageIcon,
  Palette,
  Phone,
  Save,
  Sparkles,
  Upload,
  UserCheck,
} from 'lucide-react';
import { Alert, Badge, Button, Card, CardHeader, Field, Input, PageHeader, Textarea } from '../components/ui';
import { cn } from '../lib/utils';

const HEX = /^#([0-9a-f]{6})$/i;

const COLOR_FIELDS = [
  { key: 'primary_color', label: 'Warna utama', hint: 'Dipakai untuk latar poster gelap.' },
  { key: 'secondary_color', label: 'Warna terang', hint: 'Latar terang / area teks.' },
  { key: 'accent_color', label: 'Warna aksen', hint: 'Tombol, garis, dan sorotan.' },
];

function UploadZone({ inputRef, onChange, accept, disabled, icon: Icon, title, description, busyLabel, busy }) {
  return (
    <label
      className={cn(
        'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-line bg-canvas px-4 py-5 text-center transition hover:border-brand-300 hover:bg-brand-50/40',
        (disabled || busy) && 'pointer-events-none opacity-70'
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={onChange}
        disabled={disabled || busy}
        className="sr-only"
      />
      <Icon className={cn('mb-1.5 h-6 w-6', busy ? 'text-brand-500' : 'text-ink-subtle')} aria-hidden="true" />
      <span className="text-sm font-medium text-ink">{busy ? busyLabel : title}</span>
      <span className="mt-0.5 text-[11px] text-ink-muted">{description}</span>
    </label>
  );
}

export default function BrandSetup({
  brand,
  brandForm,
  setBrandForm,
  onSave,
  saving,
  onLogoUpload,
  logoUploading,
  onTalentUpload,
  talentUploading,
}) {
  const [touched, setTouched] = useState(false);
  const logoRef = useRef(null);
  const talentRef = useRef(null);

  const update = (key, value) => setBrandForm((prev) => ({ ...prev, [key]: value }));
  const invalidColor = (value) => touched && value && !HEX.test(value);
  const companyMissing = touched && !brandForm.company?.trim();

  return (
    <div className="space-y-4">
      <PageHeader
        title="Brand & aset"
        description="Informasi ini dipakai AI untuk menyusun konten dan muncul di setiap desain. Semakin lengkap, semakin sesuai hasilnya."
        actions={
          <Badge tone={brand?.has_logo ? 'success' : 'neutral'}>
            {brand?.has_logo ? 'Logo terpasang' : 'Logo belum ada'}
          </Badge>
        }
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* Form identitas */}
        <Card className="xl:col-span-2">
          <CardHeader
            title="Identitas usaha"
            description="Dipakai untuk konteks konten, kontak di poster, dan caption."
            icon={Phone}
          />
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setTouched(true);
              if (!brandForm.company?.trim()) return;
              if (COLOR_FIELDS.some((field) => !HEX.test(brandForm[field.key] || ''))) return;
              onSave(event);
            }}
            className="space-y-4 p-5"
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Nama usaha / brand" htmlFor="brand-company" required error={companyMissing ? 'Nama usaha wajib diisi.' : undefined}>
                <Input
                  id="brand-company"
                  value={brandForm.company}
                  onChange={(event) => update('company', event.target.value)}
                  placeholder="Contoh: Kedai Kopi"
                  invalid={companyMissing}
                  maxLength={120}
                />
              </Field>

              <Field label="Bidang usaha" htmlFor="brand-industry" hint="Contoh: kedai kopi, roastery & kafe, kuliner.">
                <Input
                  id="brand-industry"
                  value={brandForm.industry}
                  onChange={(event) => update('industry', event.target.value)}
                  placeholder="Contoh: Kedai kopi & roastery lokal"
                  maxLength={160}
                />
              </Field>

              <Field label="Nomor telepon / WhatsApp" htmlFor="brand-phone" hint="Tampil di footer poster.">
                <Input
                  id="brand-phone"
                  value={brandForm.phone}
                  onChange={(event) => update('phone', event.target.value)}
                  placeholder="0812-3456-7890"
                  inputMode="tel"
                  maxLength={40}
                />
              </Field>

              <Field label="Akun Instagram" htmlFor="brand-handle" hint="Sertakan tanda @.">
                <Input
                  id="brand-handle"
                  value={brandForm.handle}
                  onChange={(event) => update('handle', event.target.value)}
                  placeholder="@kedaikopi"
                  maxLength={60}
                />
              </Field>
            </div>

            <Field
              label="Deskripsi singkat usaha"
              htmlFor="brand-description"
              hint="Jelaskan produk unggulan dan pembeli yang Anda sasar. AI memakai ini sebagai konteks."
            >
              <Textarea
                id="brand-description"
                value={brandForm.description}
                onChange={(event) => update('description', event.target.value)}
                rows={3}
                maxLength={500}
                placeholder="Contoh: Kedai kopi artisanal yang menyajikan racikan biji kopi nusantara pilihan, aneka pastry hangat, dan suasana santai untuk bekerja maupun berkumpul."
              />
            </Field>

            <Field
              label="Target pembaca"
              htmlFor="brand-audience"
              hint="Contoh: pecinta kopi, pekerja kantoran, mahasiswa."
            >
              <Input
                id="brand-audience"
                value={brandForm.audience || ''}
                onChange={(event) => update('audience', event.target.value)}
                placeholder="Contoh: pecinta kopi, pekerja WFH, anak muda & mahasiswa"
                maxLength={160}
              />
            </Field>

            <div className="border-t border-line pt-4">
              <p className="flex items-center gap-1.5 text-sm font-medium text-ink">
                <Palette className="h-4 w-4 text-brand-600" aria-hidden="true" />
                Warna khas desain
              </p>
              <p className="hint">Kode warna hex dipakai mesin desain untuk membuat poster.</p>

              <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
                {COLOR_FIELDS.map((field) => (
                  <div key={field.key} className="rounded-xl border border-line bg-canvas p-3">
                    <label htmlFor={`color-${field.key}`} className="text-xs font-medium text-ink">
                      {field.label}
                    </label>
                    <div className="mt-1.5 flex items-center gap-2">
                      <input
                        type="color"
                        aria-label={`Pilih ${field.label}`}
                        value={HEX.test(brandForm[field.key] || '') ? brandForm[field.key] : '#3E2723'}
                        onChange={(event) => update(field.key, event.target.value)}
                        className="h-9 w-9 shrink-0 cursor-pointer rounded-lg border border-line bg-surface p-0.5"
                      />
                      <input
                        id={`color-${field.key}`}
                        value={brandForm[field.key]}
                        onChange={(event) => update(field.key, event.target.value)}
                        className={cn(
                          'input px-2 py-1.5 font-mono text-xs uppercase',
                          invalidColor(brandForm[field.key]) && 'input-invalid'
                        )}
                        maxLength={7}
                        aria-invalid={invalidColor(brandForm[field.key]) || undefined}
                      />
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">{field.hint}</p>
                    {invalidColor(brandForm[field.key]) && (
                      <p className="mt-1 text-[11px] text-danger-600">Gunakan format #RRGGBB.</p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-2 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs leading-relaxed text-ink-muted">
                Perubahan berlaku untuk konten yang dibuat setelah disimpan.
              </p>
              <Button type="submit" icon={Save} loading={saving} className="w-full sm:w-auto">
                Simpan perubahan
              </Button>
            </div>
          </form>
        </Card>

        {/* Aset */}
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Logo usaha"
              icon={ImageIcon}
              actions={brand?.has_logo ? <Badge tone="success"><Check className="h-3 w-3" aria-hidden="true" /> Terpasang</Badge> : null}
            />
            <div className="space-y-3 p-5">
              <div className="flex items-center gap-3 rounded-xl border border-line bg-canvas p-3">
                <span className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-surface p-1">
                  {brand?.has_logo && brand?.logo_url ? (
                    <img src={brand.logo_url} alt="Logo usaha" className="h-full w-full object-contain" />
                  ) : (
                    <ImageIcon className="h-6 w-6 text-ink-subtle" aria-hidden="true" />
                  )}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink">{brand?.has_logo ? 'Logo aktif' : 'Belum ada logo'}</p>
                  <p className="text-[11px] leading-relaxed text-ink-muted">
                    {brand?.has_logo ? 'Muncul di header setiap slide carousel.' : 'Tanpa logo, slide tetap dibuat dengan teks brand.'}
                  </p>
                </div>
              </div>

              <UploadZone
                inputRef={logoRef}
                onChange={onLogoUpload}
                accept="image/png,image/jpeg"
                busy={logoUploading}
                busyLabel="Mengunggah logo…"
                icon={Upload}
                title={brand?.has_logo ? 'Ganti logo' : 'Pilih file logo'}
                description="PNG transparan lebih disarankan · maksimal 5 MB"
              />
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Foto model (opsional)"
              icon={UserCheck}
              actions={brand?.has_talent_ref ? <Badge tone="success"><Check className="h-3 w-3" aria-hidden="true" /> Terpasang</Badge> : null}
            />
            <div className="space-y-3 p-5">
              <Alert tone="info">
                Unggah satu foto orang (wajah atau setengah badan) tanpa pose khusus. AI lalu membuat variasi pose
                seperti tersenyum, berpikir, atau menunjuk untuk dipakai di poster.
              </Alert>

              <div className="flex items-center gap-3 rounded-xl border border-line bg-canvas p-3">
                <span className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-surface">
                  {brand?.has_talent_ref && brand?.talent_ref_url ? (
                    <img src={brand.talent_ref_url} alt="Foto model" className="h-full w-full object-cover" />
                  ) : (
                    <UserCheck className="h-6 w-6 text-ink-subtle" aria-hidden="true" />
                  )}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink">{brand?.has_talent_ref ? 'Foto model aktif' : 'Belum ada foto model'}</p>
                  <p className="text-[11px] leading-relaxed text-ink-muted">
                    {brand?.has_talent_ref
                      ? 'Dipakai AI untuk membuat pose baru saat konten butuh figur.'
                      : 'Konten tanpa figur tetap bisa dibuat.'}
                  </p>
                </div>
              </div>

              <UploadZone
                inputRef={talentRef}
                onChange={onTalentUpload}
                accept="image/png,image/jpeg"
                busy={talentUploading}
                busyLabel="Mengunggah foto…"
                icon={Sparkles}
                title={brand?.has_talent_ref ? 'Ganti foto model' : 'Pilih foto model'}
                description="Foto jelas, pencahayaan cukup, tanpa pose khusus"
              />
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
