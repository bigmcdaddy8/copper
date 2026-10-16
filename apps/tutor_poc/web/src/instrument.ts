// Tradable-price display for the instrument's tick grid (server-supplied, Laboratory CME_ES_TICK_GRID_V1).
// Used only to format labels (price axis, crosshair). Data values are never rounded.

export interface PriceGrid {
  symbol: string;
  tick_size: number;
  price_precision: number;
  policy: string;
}

/** Nearest valid tick; an exact half tick rounds up (7780.125 → 7780.25). */
export function quantizeToTick(price: number, tick: number): number {
  // Integer tick index; the tiny epsilon absorbs binary noise (7780.125 / 0.25 must be exactly half).
  return Math.round(price / tick + 1e-9) * tick;
}

export function tickPriceFormatter(grid: PriceGrid): (price: number) => string {
  return (price) => quantizeToTick(price, grid.tick_size).toFixed(grid.price_precision);
}
