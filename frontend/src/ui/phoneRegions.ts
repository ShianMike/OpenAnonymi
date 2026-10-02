export const phoneRegions = [
  ['PH', 'Philippines'],
  ['US', 'United States'],
  ['GB', 'United Kingdom'],
  ['CA', 'Canada'],
  ['AU', 'Australia'],
  ['IN', 'India'],
] as const
export const regionName = (code: string) => phoneRegions.find(([value]) => value === code)?.[1] ?? code

