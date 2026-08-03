import type { ProductOption } from '../api/types'

export interface ProductOptionGroup {
  fundGroupName: string
  options: ProductOption[]
}

/** 后端已按基金主体和份额类别排序；前端保持顺序并生成下拉分组。 */
export function groupProductOptions(options: ProductOption[]): ProductOptionGroup[] {
  const groups = new Map<string, ProductOption[]>()
  for (const option of options) {
    const items = groups.get(option.fund_group_name) ?? []
    items.push(option)
    groups.set(option.fund_group_name, items)
  }
  return [...groups].map(([fundGroupName, items]) => ({
    fundGroupName,
    options: items,
  }))
}

export function productOptionLabel(option: ProductOption) {
  return option.share_class
    ? `${option.product_name} · ${option.share_class} · ${option.product_code}`
    : `${option.product_name} · ${option.product_code}`
}
