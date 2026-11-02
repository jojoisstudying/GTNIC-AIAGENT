import { useMemo, useState } from 'react';
import { Layers, Search } from 'lucide-react';
import { Badge, Card, EmptyState, Input, PageHeader, Pills } from '../components/ui';

const ROLE_LABEL = {
  cover: 'Cover',
  penjelasan: 'Penjelasan',
  daftar: 'Daftar',
  data: 'Data',
  konteks: 'Konteks',
  langkah: 'Langkah',
  perbandingan: 'Perbandingan',
  cta: 'Ajakan bertindak',
  rangkuman: 'Rangkuman',
  bukti: 'Bukti & kutipan',
};

const ROLE_HINT = {
  cover: 'Slide pembuka yang menarik perhatian.',
  penjelasan: 'Menjelaskan satu gagasan dengan teks dan foto.',
  daftar: 'Menyajikan beberapa poin secara berurutan.',
  data: 'Menonjolkan angka atau statistik penting.',
  konteks: 'Memberi latar belakang sebelum inti pesan.',
  langkah: 'Menuntun pembaca lewat langkah demi langkah.',
  perbandingan: 'Membandingkan dua hal secara berdampingan.',
  cta: 'Mengajak pembaca melakukan sesuatu.',
  rangkuman: 'Merangkum pesan utama di akhir.',
  bukti: 'Menampilkan kutipan atau bukti pendukung.',
};

const ROLE_TONE = {
  cover: 'brand',
  penjelasan: 'neutral',
  daftar: 'neutral',
  data: 'success',
  konteks: 'neutral',
  langkah: 'warning',
  perbandingan: 'warning',
  cta: 'brand',
  rangkuman: 'success',
  bukti: 'neutral',
};

const prettify = (value) => {
  const text = String(value || '').replace(/_/g, ' ').trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : 'Layout';
};

export default function Layouts({ layouts = [], loading }) {
  const [role, setRole] = useState('all');
  const [query, setQuery] = useState('');

  const roles = useMemo(() => {
    const unique = [...new Set(layouts.map((layout) => layout.role).filter(Boolean))];
    return [{ key: 'all', label: 'Semua', count: layouts.length }, ...unique.map((item) => ({
      key: item,
      label: ROLE_LABEL[item] || item,
      count: layouts.filter((layout) => layout.role === item).length,
    }))];
  }, [layouts]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return layouts.filter((layout) => {
      const matchRole = role === 'all' || layout.role === role;
      const matchTerm =
        !term ||
        String(layout.name || layout.id || '').toLowerCase().includes(term) ||
        String(layout.description || '').toLowerCase().includes(term);
      return matchRole && matchTerm;
    });
  }, [layouts, role, query]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Template layout"
        description="Layout menentukan susunan setiap slide: judul, isi, data, perbandingan, dan ajakan bertindak. AI memilih layout yang sesuai otomatis."
      />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <Pills ariaLabel="Filter peran layout" value={role} onChange={setRole} items={roles} />
        <div className="relative w-full lg:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle" aria-hidden="true" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Cari layout…"
            className="pl-9"
            aria-label="Cari layout"
          />
        </div>
      </div>

      {loading && layouts.length === 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="card h-32 animate-pulse" aria-hidden="true" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Layers}
          title="Layout tidak ditemukan"
          description={layouts.length === 0 ? 'Daftar layout belum bisa dimuat dari server.' : 'Coba kata kunci lain atau pilih peran berbeda.'}
        />
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((layout, index) => (
            <li key={layout.id || index} className="card card-hover flex flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold leading-snug text-ink">{layout.name || prettify(layout.id)}</p>
                <Badge tone={ROLE_TONE[layout.role] || 'neutral'}>{ROLE_LABEL[layout.role] || prettify(layout.role)}</Badge>
              </div>
              <p className="mt-1.5 flex-1 text-xs leading-relaxed text-ink-muted">
                {layout.description || ROLE_HINT[layout.role] || 'Layout siap dipakai oleh perencana konten.'}
              </p>
              <div className="mt-3 flex items-center justify-between border-t border-line pt-2.5 text-[11px]">
                <span className="font-mono text-ink-subtle">{layout.id}</span>
                <span className="font-medium text-success-700">{layout.status || 'approved'}</span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Card className="p-4">
        <p className="text-xs leading-relaxed text-ink-muted">
          Template ini adalah bagian dari mesin desain. Menambah atau mengubah template dilakukan di sisi server,
          bukan dari antarmuka.
        </p>
      </Card>
    </div>
  );
}
