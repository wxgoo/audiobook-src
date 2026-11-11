// 列表分页大小：后端 get_book_list 会把 size 截断到 MAX_PAGE_SIZE（200，
// LITE_PAGE_SIZE 开启时 60）。前端如果用未截断的值算 page_cnt 与 start，
// 第二页的 offset 就会越过后端实际返回范围，表现成“尾页/第二页空白”。
export const MAX_PAGE_SIZE = 200;

export function clampPageSize(value, fallback = 0, max = MAX_PAGE_SIZE) {
  const n = parseInt(value, 10);
  if (!Number.isFinite(n) || n <= 0) {
    return fallback;
  }
  return Math.min(n, max);
}
