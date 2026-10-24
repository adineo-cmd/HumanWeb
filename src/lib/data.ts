import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export interface SiteLink {
  url: string;
  title: string;
  description: string;
}

export interface SubcategoryRef {
  id: string;
  full_path: string;
  title: string;
}

export interface Category {
  id: string;
  full_path: string;
  title: string;
  description: string;
  num_entries: number;
  subcategories: SubcategoryRef[];
  links: SiteLink[];
}

const DATA_DIR = fileURLToPath(new URL('../data/curlie/', import.meta.url));

/** Convert "Top/Arts/Animation" or "Kids_and_Teens/Arts" -> "arts/animation" / "kids-and-teens/arts" */
export function pathToSlug(fullPath: string): string {
  return fullPath
    .replace(/^Top\//i, '')
    .replace(/_/g, '-')
    .toLowerCase();
}

let cache: Map<string, Category> | null = null;

/** Load every JSON part file once per build and index by slug */
export function getAllCategories(): Map<string, Category> {
  if (cache) return cache;
  cache = new Map();

  const files = fs
    .readdirSync(DATA_DIR)
    .filter((f) => f.endsWith('.json') && f !== 'summary.json')
    .sort();

  for (const file of files) {
    const raw = fs.readFileSync(path.join(DATA_DIR, file), 'utf8');
    const data = JSON.parse(raw) as Record<string, Category>;
    for (const cat of Object.values(data)) {
      if (cat?.full_path) cache.set(pathToSlug(cat.full_path), cat);
    }
  }
  return cache;
}

export function getCategoryBySlug(slug: string): Category | undefined {
  return getAllCategories().get(slug);
}

/** Breadcrumb trail, skipping the legacy "Top" segment */
export function buildCrumbs(fullPath: string): { label: string; href?: string }[] {
  const segments = fullPath.split('/').filter((s) => s.toLowerCase() !== 'top');
  return segments.map((seg, i) => {
    const cumulative = segments.slice(0, i + 1).join('/');
    const isLast = i === segments.length - 1;
    return {
      label: seg.replace(/_/g, ' '),
      href: isLast ? undefined : `/${pathToSlug(cumulative)}`,
    };
  });
}