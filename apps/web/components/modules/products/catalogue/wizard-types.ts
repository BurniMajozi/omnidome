import type { Check, Definition, Economics, Lists, MarginMatrix, Nature, Product, ProductInput, Status, Usage } from "@/lib/catalogue-api"

export interface Form {
  id?: string
  revision?: number
  status: Status
  product_number: string
  /** Set only when the user typed a custom number; blank means server-assigned. */
  custom_number: string
  name: string
  category: string
  range: string
  family: string
  nature: Nature
  usage: Usage
  owner: string
  definition: Definition
}

export interface Preview { checks: Check[]; ready_to_launch: boolean; economics?: Economics; margin_matrix?: MarginMatrix }

export interface StepProps {
  form: Form
  set: (patch: Partial<Form>) => void
  setDef: (patch: Partial<Definition>) => void
  products: Product[]
  lists: Lists
  reloadLists: () => Promise<void>
  preview: Preview | null
  /** Saves the draft if it has no id yet and returns the id (needed before uploading files). */
  ensureSaved: () => Promise<string>
  notify: (message: string) => void
  locked: boolean
  /** Open another product's details (read-only) without leaving the editor. */
  onView: (id: string) => void
}

export function toInput(f: Form): ProductInput {
  return {
    name: f.name, category: f.category, range: f.range, family: f.family, nature: f.nature, usage: f.usage, owner: f.owner,
    product_number: f.custom_number || null, definition: f.definition,
  }
}

export function fromProduct(p: Product): Form {
  return {
    id: p.id, revision: p.revision, status: p.status, product_number: p.product_number, custom_number: "", name: p.name,
    category: p.category, range: p.range, family: p.family, nature: p.nature, usage: p.usage, owner: p.owner,
    definition: structuredClone(p.definition),
  }
}

export const NUMBER_RE = /^[A-Z0-9][A-Z0-9-]{2,23}$/
