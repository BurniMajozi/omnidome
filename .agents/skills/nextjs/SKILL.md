---
name: nextjs
description: "Production-grade Next.js App Router engineering guide based on official Vercel Next.js standards (https://github.com/vercel/next.js.git). Covers eliminating client-side mock stubs with real Route Handlers (app/api/**/route.ts), Server Actions, Server vs. Client component boundaries, typed API layers, optimistic mutations, error boundaries, streaming, and caching."
---

# Next.js App Router Production Engineering Skill

This skill enforces official Next.js App Router architecture and conventions from [vercel/next.js](https://github.com/vercel/next.js.git). It guides transforming mock-heavy, stubbed interfaces into fully functional, production-grade applications.

## Core Directives

### 1. Eliminate Mock Stubs & Static Dummies
- **Rule**: Never leave static arrays (`defaultX = [...]`) as unbacked state in production views.
- **Implementation**:
  - Create dedicated Route Handlers under `apps/web/app/api/.../route.ts`.
  - Provide a typed client API service module (`apps/web/lib/...-api.ts`) exporting clean async functions (`fetchX`, `createX`, `updateX`, `deleteX`).
  - Wire UI components to real fetch hooks with loading skeletons, error states, and optimistic UI updates.
  - Retain static constants solely as initial placeholders during first render or fallback if the backend service is offline.

### 2. Server vs. Client Component Boundaries
- **Server Components (Default)**: Use for data fetching, direct DB queries, static rendering, and heavy dependencies that don't need browser APIs.
- **Client Components (`"use client"`)**: Use only at the leaves of the component tree where user interaction, event listeners (`onClick`, `onChange`), React hooks (`useState`, `useEffect`, `useMemo`), or browser APIs are required.
- **Composition Pattern**: Pass Server Components as children to Client Component wrappers to preserve server-side streaming.

### 3. Route Handlers (`app/api/**/route.ts`)
Follow standard Next.js 14/15/16 App Router Route Handler signatures:

```ts
import { NextResponse, type NextRequest } from "next/server"

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const filter = searchParams.get("filter")
    // Retrieve from database or backend microservice
    return NextResponse.json({ success: true, data: items }, { status: 200 })
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : "Internal Error" },
      { status: 500 }
    )
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    // Validate schema & persist
    return NextResponse.json({ success: true, data: createdItem }, { status: 201 })
  } catch (error) {
    return NextResponse.json({ success: false, error: "Invalid payload" }, { status: 400 })
  }
}
```

### 4. Optimistic UI & Mutation Resilience
- Perform instant optimistic updates in local React state so the interface feels snappy.
- In the background, dispatch the `POST`/`PUT`/`DELETE` request to the Next.js Route Handler.
- If the server request fails, rollback the local state and display a clear, accessible error notification.

### 5. Resilient Error Handling & Degraded Modes
- In microservice or multi-tenant architectures, a temporary outage in one downstream service must never cause a 500 crash on the entire dashboard page.
- Degrade gracefully to cached or fallback states with an explicit "Offline / Degraded Mode" badge so users can still navigate and use unaffected features.

### 6. Caching & Revalidation
- Use Next.js fetch cache options (`cache: "no-store"` for real-time transactional views, or `{ next: { revalidate: 60 } }` for semi-static dashboards).
- Revalidate on mutation using `revalidatePath()` or `revalidateTag()`.
