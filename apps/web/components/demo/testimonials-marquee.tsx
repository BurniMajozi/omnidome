"use client"

import { cn } from "@/lib/utils"
import { Marquee } from "@/components/ui/marquee"

const reviews = [
  {
    name: "Thabo Molefe",
    username: "@thabo_m",
    body: "OmniDome transformed how we handle customer support. Response times dropped by 60% and our team finally has time to focus on growth.",
    img: "https://avatar.vercel.sh/thabo",
  },
  {
    name: "Priya Naidoo",
    username: "@priya_n",
    body: "The billing automation alone saved us 20 hours a week. No more chasing payments or manual reconciliations. Game changer!",
    img: "https://avatar.vercel.sh/priya",
  },
  {
    name: "Johan van der Merwe",
    username: "@johan_vdm",
    body: "We went from juggling 5 different systems to one unified platform. Our operations team couldn't be happier.",
    img: "https://avatar.vercel.sh/johan",
  },
  {
    name: "Lerato Dlamini",
    username: "@lerato_d",
    body: "Customer churn dropped by 35% after implementing the AI retention features. The predictive analytics are incredibly accurate.",
    img: "https://avatar.vercel.sh/lerato",
  },
  {
    name: "Rajesh Pillay",
    username: "@rajesh_p",
    body: "Finally, a platform built for South African ISPs. Load shedding notifications, RICA compliance, everything just works.",
    img: "https://avatar.vercel.sh/rajesh",
  },
  {
    name: "Sarah Thompson",
    username: "@sarah_t",
    body: "The network monitoring saved us from a major outage last month. We caught the issue before customers even noticed.",
    img: "https://avatar.vercel.sh/sarah",
  },
  {
    name: "Pieter Botha",
    username: "@pieter_b",
    body: "Our sales team closed 40% more deals after switching to OmniDome. The CRM integration is seamless.",
    img: "https://avatar.vercel.sh/pieter",
  },
  {
    name: "Anisha Govender",
    username: "@anisha_g",
    body: "Best investment we made this year. ROI was positive within the first quarter. Highly recommend to any ISP.",
    img: "https://avatar.vercel.sh/anisha",
  },
  {
    name: "Michael Edwards",
    username: "@michael_e",
    body: "The customer portal reduced our support calls by half. Customers can now manage everything themselves.",
    img: "https://avatar.vercel.sh/michael",
  },
  {
    name: "Lizelle du Plessis",
    username: "@lizelle_dp",
    body: "From Cape Town to Joburg, we manage all our branches from one dashboard. Scaling has never been easier.",
    img: "https://avatar.vercel.sh/lizelle",
  },
  {
    name: "Vikram Sharma",
    username: "@vikram_s",
    body: "The AI-powered insights helped us identify upselling opportunities we never knew existed. Revenue up 25%!",
    img: "https://avatar.vercel.sh/vikram",
  },
  {
    name: "Naledi Khumalo",
    username: "@naledi_k",
    body: "Support response times went from hours to minutes. Our customers have never been happier.",
    img: "https://avatar.vercel.sh/naledi",
  },
  {
    name: "Willem Pretorius",
    username: "@willem_p",
    body: "Die platform is uitstekend! Finally something that understands the unique challenges of running an ISP in SA.",
    img: "https://avatar.vercel.sh/willem",
  },
  {
    name: "James Mitchell",
    username: "@james_m",
    body: "Migrating from our old system was seamless. The team support during onboarding was exceptional.",
    img: "https://avatar.vercel.sh/james",
  },
]

const firstRow = reviews.slice(0, reviews.length / 2)
const secondRow = reviews.slice(reviews.length / 2)

const ReviewCard = ({
  img,
  name,
  username,
  body,
}: {
  img: string
  name: string
  username: string
  body: string
}) => {
  return (
    <figure
      className={cn(
        "relative h-full w-72 cursor-pointer overflow-hidden rounded-xl border p-4",
        // light styles
        "border-gray-950/[.1] bg-gray-950/[.01] hover:bg-gray-950/[.05]",
        // dark styles
        "dark:border-gray-50/[.1] dark:bg-gray-50/[.10] dark:hover:bg-gray-50/[.15]"
      )}
    >
      <div className="flex flex-row items-center gap-3">
        <img className="rounded-full" width="40" height="40" alt="" src={img} />
        <div className="flex flex-col">
          <figcaption className="text-sm font-medium dark:text-white">
            {name}
          </figcaption>
          <p className="text-xs font-medium text-muted-foreground">{username}</p>
        </div>
      </div>
      <blockquote className="mt-3 text-sm text-muted-foreground leading-relaxed">{body}</blockquote>
    </figure>
  )
}

export function TestimonialsMarquee() {
  return (
    <section className="py-20 px-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold mb-4 text-foreground">
            Don't Take Our Word for It
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Hear What Our Community Has to Say
          </p>
        </div>

        {/* Marquee */}
        <div className="relative flex w-full flex-col items-center justify-center overflow-hidden">
          <Marquee pauseOnHover className="[--duration:40s]">
            {firstRow.map((review) => (
              <ReviewCard key={review.username} {...review} />
            ))}
          </Marquee>
          <Marquee reverse pauseOnHover className="[--duration:40s]">
            {secondRow.map((review) => (
              <ReviewCard key={review.username} {...review} />
            ))}
          </Marquee>
          <div className="from-background pointer-events-none absolute inset-y-0 left-0 w-1/4 bg-gradient-to-r"></div>
          <div className="from-background pointer-events-none absolute inset-y-0 right-0 w-1/4 bg-gradient-to-l"></div>
        </div>
      </div>
    </section>
  )
}
