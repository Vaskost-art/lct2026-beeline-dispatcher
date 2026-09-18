/** Обращение к сервису: конверт снимается здесь, дальше живут только данные. */

/** Ошибка сервиса: код для развилки на экране, сообщение для человека. */
export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface Envelope<T> {
  ok: boolean;
  data?: T;
  error?: { code: string; message: string };
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let answer: Response;
  try {
    answer = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch {
    // Обрыв связи выглядит для человека так же, как отказ сервиса, но
    // повторять его имеет смысл, а отказ по коду нет.
    throw new ApiError('network', 'Сервис не отвечает. Проверьте связь');
  }

  const body = (await answer.json().catch(() => null)) as Envelope<T> | null;
  if (!answer.ok || !body || body.ok !== true) {
    const error = body?.error;
    throw new ApiError(error?.code ?? 'error', error?.message ?? 'Не удалось выполнить запрос');
  }
  return body.data as T;
}

/** Запрос с телом: все изменяющие ручки сервиса принимают JSON. */
export function send<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) });
}
