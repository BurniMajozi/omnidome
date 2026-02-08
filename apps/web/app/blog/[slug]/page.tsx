import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Clock, Calendar } from "lucide-react";
import { FlickeringGrid } from "@/components/ui/flickering-grid";

// Blog posts data - matches the data in the blog listing page
const blogPosts: Record<string, {
  title: string;
  description: string;
  date: string;
  tags: string[];
  thumbnail?: string;
  readTime: string;
  content: string;
}> = {
  "ai-churn-prediction-isps": {
    title: "How AI Churn Prediction is Revolutionizing ISP Customer Retention",
    description: "Learn how South African ISPs are using predictive analytics to identify at-risk customers before they leave.",
    date: "2026-01-20",
    tags: ["AI", "Retention", "Analytics"],
    thumbnail: "/predict-churn-with-ai.png",
    readTime: "8 min read",
    content: `
## The Challenge of Customer Churn

Customer churn is one of the biggest challenges facing South African ISPs today. With competition intensifying and customers having more choices than ever, retaining existing customers is more cost-effective than acquiring new ones.

Traditional approaches to customer retention are reactive—by the time you know a customer wants to leave, it's often too late. That's where AI-powered churn prediction comes in.

## How AI Churn Prediction Works

OmniDome's Retention Dome uses machine learning algorithms to analyze customer behavior patterns and identify early warning signs of churn:

- **Usage patterns**: Declining bandwidth usage or service utilization
- **Support interactions**: Increasing complaint frequency or unresolved tickets
- **Payment behavior**: Late payments or declined transactions
- **Engagement metrics**: Reduced login frequency to customer portal

## Key Benefits for ISPs

### 1. Proactive Intervention
Instead of waiting for cancellation requests, your retention team can reach out to at-risk customers with personalized offers before they consider leaving.

### 2. Resource Optimization
Focus your retention efforts on customers who are actually at risk, rather than blanket campaigns that waste resources.

### 3. Improved Customer Experience
By addressing issues before they escalate, you're demonstrating that you value the customer relationship.

## Getting Started

OmniDome's AI churn prediction is available as part of the Retention Dome module. Contact our team to schedule a demo and see how it can work for your ISP.
    `,
  },
  "unified-communications-guide": {
    title: "The Complete Guide to Unified Communications for ISPs",
    description: "Discover how to streamline customer interactions across email, SMS, WhatsApp, and voice in one platform.",
    date: "2026-01-15",
    tags: ["Communications", "Product Updates", "Guide"],
    thumbnail: "/unified-communication.png",
    readTime: "12 min read",
    content: `
## Why Unified Communications Matter

Modern customers expect to reach you on their preferred channel. Some prefer email, others WhatsApp, and many still want to call. Managing these channels separately creates silos and frustrates both customers and staff.

## The OmniDome Approach

Communication Dome brings all your customer interactions into a single, unified inbox:

### Supported Channels
- **Email**: Full inbox with threading and templates
- **SMS**: Two-way messaging with delivery tracking
- **WhatsApp Business**: API integration for rich media support
- **Voice**: Call logging, recording, and AI transcription

### Key Features

#### 1. Unified Customer Timeline
See every interaction with a customer, regardless of channel, in a single chronological view.

#### 2. Smart Routing
Automatically route conversations to the right team member based on skills, availability, and customer history.

#### 3. AI-Powered Responses
Suggest responses based on common queries and customer context, reducing response time by up to 60%.

#### 4. Automation Workflows
Set up automated responses for common queries, appointment confirmations, and payment reminders.

## Implementation Best Practices

1. Start with your highest-volume channels
2. Train your team on the unified interface
3. Set up automation gradually
4. Monitor response time metrics

## Conclusion

Unified communications isn't just about efficiency—it's about providing the seamless experience your customers expect.
    `,
  },
  "sales-automation-best-practices": {
    title: "5 Sales Automation Best Practices for Growing ISPs",
    description: "From lead scoring to automated follow-ups, these strategies will help your sales team close more deals.",
    date: "2026-01-10",
    tags: ["Sales", "Automation", "Best Practices"],
    thumbnail: "/unified-sales.png",
    readTime: "6 min read",
    content: `
## Introduction

Sales automation isn't about replacing your sales team—it's about empowering them to focus on what they do best: building relationships and closing deals.

## Best Practice #1: Implement Lead Scoring

Not all leads are created equal. Use behavioral data to score leads based on:
- Website engagement
- Email opens and clicks
- Coverage area (are they in your service area?)
- Business size and potential value

## Best Practice #2: Automate Follow-ups

The fortune is in the follow-up. Set up automated email sequences that:
- Send immediately after form submission
- Follow up 2 days later with more information
- Send a final reminder at day 7

## Best Practice #3: Use Pipeline Automation

Move deals through your pipeline automatically based on actions:
- Proposal sent → Automatically move to "Proposal Stage"
- Contract signed → Trigger provisioning workflow
- Payment received → Update to "Won"

## Best Practice #4: Integrate with Your CRM

Your sales automation should feed directly into your CRM to maintain a single source of truth.

## Best Practice #5: Measure and Optimize

Track key metrics:
- Lead response time
- Conversion rates by stage
- Average deal cycle length
- Revenue per sales rep

## Getting Started with Sales Dome

OmniDome's Sales Dome includes all these automation capabilities out of the box. Schedule a demo to see it in action.
    `,
  },
  "product-catalog-management": {
    title: "Agentic AI: The Future of Product Catalog Management",
    description: "How autonomous AI agents are transforming how ISPs manage their fiber and LTE product offerings.",
    date: "2026-01-05",
    tags: ["AI", "Products", "Product Updates"],
    thumbnail: "/agentic-ai-product-management.png",
    readTime: "10 min read",
    content: `
## What is Agentic AI?

Agentic AI represents the next evolution in artificial intelligence—systems that can take autonomous actions to achieve goals, rather than just responding to queries.

## Agentic AI in Product Management

For ISPs managing complex product catalogs with multiple speed tiers, bundle options, and promotional pricing, Agentic AI can:

### 1. Optimize Pricing Automatically
Analyze competitor pricing, demand patterns, and margin requirements to suggest optimal pricing strategies.

### 2. Manage Promotions
Create, launch, and expire promotional offers based on business rules and market conditions.

### 3. Handle Product Lifecycle
Automatically sunset old products, migrate customers to new offerings, and manage phase-out communications.

### 4. Generate Product Descriptions
Create compelling, SEO-optimized product descriptions for your website and marketing materials.

## Real-World Example

One of our ISP clients used Agentic AI to:
- Reduce product management time by 75%
- Increase average revenue per user by 12%
- Launch new products 3x faster

## The Future is Autonomous

As AI capabilities continue to advance, we'll see more autonomous management of routine tasks, freeing your team to focus on strategy and customer relationships.
    `,
  },
  "popia-compliance-checklist": {
    title: "POPIA Compliance Checklist for South African ISPs",
    description: "Ensure your ISP meets all Protection of Personal Information Act requirements with this comprehensive guide.",
    date: "2025-12-28",
    tags: ["Compliance", "POPIA", "Guide"],
    readTime: "15 min read",
    content: `
## Understanding POPIA

The Protection of Personal Information Act (POPIA) is South Africa's data protection legislation. As an ISP, you handle sensitive customer data daily, making compliance essential.

## The Compliance Checklist

### 1. Data Inventory
- [ ] Document all personal data you collect
- [ ] Map where data is stored
- [ ] Identify who has access

### 2. Lawful Processing
- [ ] Ensure you have consent for data collection
- [ ] Document the purpose of data processing
- [ ] Implement data minimization

### 3. Customer Rights
- [ ] Provide access to personal data on request
- [ ] Enable data correction
- [ ] Allow data deletion (where legally permitted)

### 4. Security Measures
- [ ] Implement encryption at rest and in transit
- [ ] Regular security audits
- [ ] Employee training on data handling

### 5. Breach Procedures
- [ ] Incident response plan
- [ ] Information Regulator notification process
- [ ] Customer notification templates

## How OmniDome Helps

OmniDome's Compliance Dome includes:
- Automated consent management
- Data access request handling
- Audit trail logging
- Breach notification workflows

## Conclusion

POPIA compliance isn't optional—it's essential for building trust with your customers and avoiding significant penalties.
    `,
  },
  "customer-portal-best-practices": {
    title: "Building a World-Class Customer Self-Service Portal",
    description: "Reduce support tickets by 60% with these customer portal design principles and features.",
    date: "2025-12-20",
    tags: ["Customer Portal", "Best Practices", "Support"],
    readTime: "9 min read",
    content: `
## The Power of Self-Service

Modern customers prefer to help themselves. A well-designed customer portal can reduce support tickets by 60% while improving customer satisfaction.

## Essential Portal Features

### 1. Account Overview
- Current plan and usage
- Billing history and upcoming payments
- Service status

### 2. Self-Service Actions
- Upgrade/downgrade plans
- Add services
- Update payment methods
- Manage contact details

### 3. Support Integration
- Knowledge base search
- Ticket submission and tracking
- Live chat escalation

### 4. Usage Analytics
- Bandwidth usage graphs
- Data consumption trends
- Speed test history

## Design Principles

### Mobile-First
Over 70% of portal access is from mobile devices. Design for mobile first.

### Speed Matters
Every second of load time increases abandonment. Optimize for performance.

### Clear Navigation
Customers should find what they need in 3 clicks or less.

## OmniDome Portal Dome

Our white-label customer portal includes all these features and more, fully branded to your ISP.
    `,
  },
  "network-monitoring-essentials": {
    title: "Network Monitoring Essentials: What Every ISP Should Track",
    description: "From uptime metrics to bandwidth utilization, learn which KPIs matter most for network operations.",
    date: "2025-12-15",
    tags: ["Network", "Monitoring", "Guide"],
    readTime: "11 min read",
    content: `
## Why Network Monitoring Matters

Network issues directly impact customer experience. Proactive monitoring helps you identify and resolve problems before customers notice.

## Essential Metrics

### 1. Availability/Uptime
- Target: 99.9% or higher
- Measure at multiple points in your network

### 2. Latency
- Average round-trip time
- Jitter (latency variation)

### 3. Bandwidth Utilization
- Peak usage times
- Capacity planning data

### 4. Packet Loss
- Should be below 0.1% for quality service

### 5. Error Rates
- Interface errors
- CRC errors

## Monitoring Tools

OmniDome's Network Dome provides:
- Real-time dashboards
- Automated alerting
- Historical trending
- Integration with major NOC tools

## Alerting Best Practices

- Set thresholds based on impact, not arbitrary numbers
- Use escalation procedures
- Avoid alert fatigue with intelligent grouping

## Conclusion

Good network monitoring is the foundation of excellent customer experience.
    `,
  },
  "omnidome-q1-2026-updates": {
    title: "OmniDome Q1 2026: New Features and Improvements",
    description: "A roundup of all the new features, integrations, and improvements released this quarter.",
    date: "2025-12-10",
    tags: ["Product Updates", "Announcements"],
    readTime: "5 min read",
    content: `
## Q1 2026 Highlights

We're excited to share what we've been working on this quarter!

## New Features

### AI Churn Prediction
Our new AI-powered churn prediction is now available in Retention Dome. Early users are seeing 25% improvement in retention rates.

### WhatsApp Business Integration
Full WhatsApp Business API integration is now live in Communication Dome, including rich media support.

### Agentic AI for Products
Products Dome now includes autonomous AI agents for catalog management.

## Improvements

- **Performance**: 40% faster dashboard loading
- **Mobile**: Redesigned mobile experience
- **Reports**: New custom report builder

## Integrations

New integrations this quarter:
- Sage accounting
- Xero
- Popular South African payment gateways

## What's Next

In Q2, we're focusing on:
- Enhanced analytics
- More AI capabilities
- Additional integrations

## Thank You

Thank you for being part of the OmniDome community. Your feedback drives our roadmap.
    `,
  },
};

const formatDate = (date: Date): string => {
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
};

interface PageProps {
  params: Promise<{ slug: string }>;
}

export default async function BlogPost({ params }: PageProps) {
  const { slug } = await params;

  const post = blogPosts[slug];

  if (!post) {
    notFound();
  }

  const date = new Date(post.date);
  const formattedDate = formatDate(date);

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

      <div className="space-y-4 border-b border-border relative z-10">
        <div className="max-w-4xl mx-auto flex flex-col gap-6 p-6 pt-8">
          <div className="flex flex-wrap items-center gap-3 gap-y-5 text-sm text-muted-foreground">
            <Link
              href="/blog"
              className="inline-flex items-center justify-center h-8 w-8 rounded-md border border-border hover:bg-muted transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span className="sr-only">Back to all articles</span>
            </Link>
            {post.tags && post.tags.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {post.tags.map((tag: string) => (
                  <span
                    key={tag}
                    className="h-6 w-fit px-3 text-xs font-medium bg-muted text-muted-foreground rounded-md border flex items-center justify-center"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>

          <h1 className="text-3xl md:text-4xl lg:text-5xl font-medium tracking-tighter text-balance">
            {post.title}
          </h1>

          <p className="text-muted-foreground max-w-3xl md:text-lg">
            {post.description}
          </p>

          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Calendar className="h-4 w-4" />
              {formattedDate}
            </span>
            <span className="flex items-center gap-1.5">
              <Clock className="h-4 w-4" />
              {post.readTime}
            </span>
          </div>
        </div>
      </div>

      {post.thumbnail && (
        <div className="max-w-4xl mx-auto px-6 py-8">
          <div className="relative w-full aspect-video rounded-xl overflow-hidden border border-border">
            <Image
              src={post.thumbnail}
              alt={post.title}
              fill
              className="object-cover"
              priority
            />
          </div>
        </div>
      )}

      <article className="max-w-4xl mx-auto px-6 pb-16">
        <div className="prose prose-lg dark:prose-invert max-w-none prose-headings:tracking-tight prose-h2:text-2xl prose-h3:text-xl prose-p:text-muted-foreground prose-li:text-muted-foreground prose-a:text-primary prose-a:no-underline hover:prose-a:underline">
          {post.content.split('\n').map((paragraph, index) => {
            if (paragraph.startsWith('## ')) {
              return <h2 key={index} className="text-foreground mt-8 mb-4">{paragraph.replace('## ', '')}</h2>;
            }
            if (paragraph.startsWith('### ')) {
              return <h3 key={index} className="text-foreground mt-6 mb-3">{paragraph.replace('### ', '')}</h3>;
            }
            if (paragraph.startsWith('#### ')) {
              return <h4 key={index} className="text-foreground mt-4 mb-2 font-semibold">{paragraph.replace('#### ', '')}</h4>;
            }
            if (paragraph.startsWith('- ')) {
              return <li key={index} className="ml-4">{paragraph.replace('- ', '')}</li>;
            }
            if (paragraph.startsWith('- [ ] ')) {
              return <li key={index} className="ml-4 list-none flex items-center gap-2"><input type="checkbox" disabled className="rounded" />{paragraph.replace('- [ ] ', '')}</li>;
            }
            if (paragraph.trim() === '') {
              return null;
            }
            return <p key={index} className="mb-4">{paragraph}</p>;
          })}
        </div>
      </article>

      {/* Related Articles CTA */}
      <div className="border-t border-border py-12 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-2xl font-semibold mb-4">Want to learn more?</h2>
          <p className="text-muted-foreground mb-6">
            Explore more articles or get in touch with our team.
          </p>
          <div className="flex justify-center gap-4">
            <Link
              href="/blog"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-border hover:bg-muted transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              All Articles
            </Link>
            <Link
              href="/#contact"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Contact Us
            </Link>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-border py-12 px-6">
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

export async function generateStaticParams() {
  return Object.keys(blogPosts).map((slug) => ({ slug }));
}
