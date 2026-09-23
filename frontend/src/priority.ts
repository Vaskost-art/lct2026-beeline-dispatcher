/** Метка ступени приоритета: авария, подключение, остальное.

Три ступени задал постановщик. Нижнюю не отмечаем вовсе: метка на каждой
строке перестаёт значить что-либо.
*/
export function priorityMark(priority: string | undefined): { text: string; tone: string } | null {
  const value = (priority ?? '').toLowerCase();
  if (value.startsWith('срочн')) return { text: 'авария', tone: 'bg-danger-soft text-danger' };
  if (value.startsWith('повыш')) return { text: 'подключение', tone: 'bg-warn-soft text-warn' };
  return null;
}
