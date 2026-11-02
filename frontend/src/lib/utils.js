import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Gabungkan className dengan aman (clsx + tailwind-merge). */
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
