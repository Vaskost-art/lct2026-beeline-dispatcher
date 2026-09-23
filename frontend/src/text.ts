/** Согласование числительных: «1 заявка», «2 заявки», «5 заявок». */
export function plural(count: number, one: string, few: string, many: string): string {
  const tens = count % 100;
  if (tens >= 11 && tens <= 14) return many;
  const units = count % 10;
  if (units === 1) return one;
  if (units >= 2 && units <= 4) return few;
  return many;
}

/** Дробное число по-русски: «158,5», а не «158.5». */
export function decimal(value: number, digits = 1): string {
  return value.toFixed(digits).replace('.', ',');
}
