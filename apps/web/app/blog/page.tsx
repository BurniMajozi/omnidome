import { Suspense } from "react";
import Link from "next/link";
import { BlogCard } from "@/components/blog/blog-card";
import { TagFilter } from "@/components/blog/tag-filter";
import { FlickeringGrid } from "@/components/ui/flickering-grid";
import { ArrowLeft } from "lucide-react";

// Blog posts data - can be replaced with MDX/CMS later
const blogPosts = [
  {
    slug: "ai-churn-prediction-isps",
    title: "How AI Churn Prediction is Revolutionizing ISP Customer Retention",
    description: "Learn how South African ISPs are using predictive analytics to identify at-risk customers before they leave.",
    date: "2026-01-20",
    tags: ["AI", "Retention", "Analytics"],
    thumbnail: "/predict-churn-with-ai.png",
    readTime: "8 min read",
  },
  {
    slug: "unified-communications-guide",
    title: "The Complete Guide to Unified Communications for ISPs",
    description: "Discover how to streamline customer interactions across email, SMS, WhatsApp, and voice in one platform.",
    date: "2026-01-15",
    tags: ["Communications", "Product Updates", "Guide"],
    thumbnail: "/unified-communication.png",
    readTime: "12 min read",
  },
  {
    slug: "sales-automation-best-practices",
    title: "5 Sales Automation Best Practices for Growing ISPs",
    description: "From lead scoring to automated follow-ups, these strategies will help your sales team close more deals.",
    date: "2026-01-10",
    tags: ["Sales", "Automation", "Best Practices"],
    thumbnail: "/unified-sales.png",
    readTime: "6 min read",
  },
  {
    slug: "product-catalog-management",
    title: "Agentic AI: The Future of Product Catalog Management",
    description: "How autonomous AI agents are transforming how ISPs manage their fiber and LTE product offerings.",
    date: "2026-01-05",
    tags: ["AI", "Products", "Product Updates"],
    thumbnail: "/agentic-ai-product-management.png",
    readTime: "10 min read",
  },
  {
    slug: "popia-compliance-checklist",
    title: "POPIA Compliance Checklist for South African ISPs",
    description: "Ensure your ISP meets all Protection of Personal Information Act requirements with this comprehensive guide.",
    date: "2025-12-28",
    tags: ["Compliance", "POPIA", "Guide"],
    readTime: "15 min read",
  },
  {
    slug: "customer-portal-best-practices",
    title: "Building a World-Class Customer Self-Service Portal",
    description: "Reduce support tickets by 60% with these customer portal design principles and features.",
    date: "2025-12-20",
    tags: ["Customer Portal", "Best Practices", "Support"],
    readTime: "9 min read",
  },
  {
    slug: "network-monitoring-essentials",
    title: "Network Monitoring Essentials: What Every ISP Should Track",
    description: "From uptime metrics to bandwidth utilization, learn which KPIs matter most for network operations.",
    date: "2025-12-15",
    tags: ["Network", "Monitoring", "Guide"],
    readTime: "11 min read",
  },
  {
    slug: "omnidome-q1-2026-updates",
    title: "OmniDome Q1 2026: New Features and Improvements",
    description: "A roundup of all the new features, integrations, and improvements released this quarter.",
    date: "2025-12-10",
    tags: ["Product Updates", "Announcements"],
    readTime: "5 min read",
  },
];

const formatDate = (date: Date): string => {
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
};

export default async function BlogPage({
  searchParams,
}: {
  searchParams: Promise<{ tag?: string }>;
}) {
  const resolvedSearchParams = await searchParams;
  const sortedBlogs = [...blogPosts].sort((a, b) => {
    const dateA = new Date(a.date).getTime();
    const dateB = new Date(b.date).getTime();
    return dateB - dateA;
  });

  const allTags = [
    "All",
    ...Array.from(
      new Set(sortedBlogs.flatMap((blog) => blog.tags || []))
    ).sort(),
  ];

  const selectedTag = resolvedSearchParams.tag || "All";
  const filteredBlogs =
    selectedTag === "All"
      ? sortedBlogs
      : sortedBlogs.filter((blog) => blog.tags?.includes(selectedTag));

  const tagCounts = allTags.reduce((acc, tag) => {
    if (tag === "All") {
      acc[tag] = sortedBlogs.length;
    } else {
      acc[tag] = sortedBlogs.filter((blog) =>
        blog.tags?.includes(tag)
      ).length;
    }
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="min-h-screen bg-background relative">
      <div className="absolute top-0 left-0 z-0 w-full h-[200px] [mask-image:linear-gradient(to_top,transparent_25%,black_95%)]">
        <FlickeringGrid
          className="absolute top-0 left-0 size-full"
          squareSize={4}
          gridGap={6}
          color="#6B7280"
          maxOpacity={0.2}
          flickerChance={0.05}
        />
      </div>
      
      <div className="p-6 border-b border-border flex flex-col gap-6 min-h-[250px] justify-center relative z-10">
        <div className="max-w-7xl mx-auto w-full">
          <Link 
            href="/" 
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Home
          </Link>
          <div className="flex flex-col gap-2">
            <h1 className="font-medium text-4xl md:text-5xl tracking-tighter">
              OmniDome Blog
            </h1>
            <p className="text-muted-foreground text-sm md:text-base lg:text-lg">
              ISP industry insights, product updates, and best practices for South African service providers.
            </p>
          </div>
        </div>
        {allTags.length > 0 && (
          <div className="max-w-7xl mx-auto w-full">
            <TagFilter
              tags={allTags}
              selectedTag={selectedTag}
              tagCounts={tagCounts}
            />
          </div>
        )}
      </div>

      <div className="max-w-7xl mx-auto w-full px-6 lg:px-0">
        <Suspense fallback={<div className="p-8 text-center text-muted-foreground">Loading articles...</div>}>
          <div
            className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 relative overflow-hidden border-x border-border ${
              filteredBlogs.length < 4 ? "border-b" : "border-b-0"
            }`}
          >
            {filteredBlogs.map((blog, index) => {
              const date = new Date(blog.date);
              const formattedDate = formatDate(date);

              return (
                <BlogCard
                  key={blog.slug}
                  url={`/blog/${blog.slug}`}
                  title={blog.title}
                  description={blog.description}
                  date={formattedDate}
                  thumbnail={blog.thumbnail}
                  showRightBorder={filteredBlogs.length < 3 || (index + 1) % 3 !== 0}
                />
              );
            })}
          </div>
        </Suspense>
      </div>
      
      {/* Footer */}
      <footer className="border-t border-border py-12 px-6 mt-16">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <img src="/logo-new.svg" alt="OmniDome" className="h-8 w-8" />
            <span className="font-semibold">OmniDome</span>
          </div>
          <p className="text-sm text-muted-foreground">
            © 2026 OmniDome. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
