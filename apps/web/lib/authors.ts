export interface Author {
  name: string;
  position: string;
  avatar: string;
}

export const authors: Record<string, Author> = {
  team: {
    name: "OmniDome Team",
    position: "Product Team",
    avatar: "/logo-new.svg",
  },
  support: {
    name: "Support Team",
    position: "Customer Success",
    avatar: "/logo-new.svg",
  },
} as const;

export type AuthorKey = keyof typeof authors;

export function getAuthor(key: AuthorKey): Author {
  return authors[key];
}

export function isValidAuthor(key: string): key is AuthorKey {
  return key in authors;
}
