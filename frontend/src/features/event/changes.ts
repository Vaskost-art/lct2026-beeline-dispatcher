/** Подписи изменений в предпросмотре события и их порядок в списке. */
export const STATUS_TITLES: Record<string, string> = {
  moved: 'передана другой бригаде',
  resequenced: 'сменила место в маршруте',
  retimed: 'визит сдвинут',
  dropped: 'выпала из плана',
  added: 'добавлена в план',
  frozen: 'уже начата, не трогаем',
  cancelled: 'снята с плана',
  rescued: 'вернулась в план',
};

/** Выпавшая заявка идёт первой: именно по ней звонить клиенту, а в общем
    порядке она терялась среди «сменила место в маршруте». */
export const STATUS_WEIGHT: Record<string, number> = {
  dropped: 0,
  cancelled: 1,
  added: 2,
  rescued: 3,
  moved: 4,
  retimed: 5,
  resequenced: 6,
};
