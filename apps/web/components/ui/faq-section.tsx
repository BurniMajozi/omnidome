import * as Accordion from '@radix-ui/react-accordion';
import { ChevronDownIcon } from '@radix-ui/react-icons';
import React from 'react';

const FAQS = [
  {
    question: 'What type of automation can OmniDome build for my business?',
    answer: 'OmniDome can build a wide range of automations tailored to your business needs, including workflow automation, data integration, reporting, customer communication, and more.'
  },
  {
    question: 'What is the typical project timeline?',
    answer: 'Project timelines vary based on complexity, but most automations are delivered within 2-6 weeks from project kickoff.'
  },
  {
    question: 'Do I need technical knowledge to use the automations?',
    answer: 'No technical knowledge is required. Our solutions are designed to be user-friendly and we provide full training and support.'
  },
  {
    question: 'What tools and platforms do you integrate with?',
    answer: 'We integrate with a wide variety of tools and platforms including CRMs, ERPs, cloud services, and custom APIs.'
  },
  {
    question: 'How much can automation actually save my business?',
    answer: 'Savings depend on your current processes, but automation typically reduces manual effort by 30-70%, leading to significant cost and time savings.'
  },
  {
    question: 'Is my business data secure with OmniDome?',
    answer: 'Yes, we follow industry best practices for data security and compliance to ensure your business data is protected.'
  },
  {
    question: "What's your pricing?",
    answer: 'Our pricing is flexible and based on the scope of automation required. Contact us for a custom quote.'
  }
];

export function FAQSection() {
  return (
    <section className="py-24 px-4 sm:px-6 lg:px-8 bg-background border-t border-border">
      <div className="mx-auto max-w-3xl text-center mb-12">
        <h2 className="text-4xl sm:text-5xl font-black mb-4 text-foreground">Frequently Asked Questions</h2>
        <p className="text-lg text-muted-foreground">Everything you need to know about our automation services and how we can help scale your business.</p>
      </div>
      <Accordion.Root type="single" collapsible className="space-y-4 max-w-2xl mx-auto">
        {FAQS.map((faq, idx) => (
          <Accordion.Item key={idx} value={faq.question} className="bg-muted/50 rounded-lg shadow">
            <Accordion.Header>
              <Accordion.Trigger className="group flex w-full items-center justify-between px-6 py-5 text-lg font-semibold text-left text-foreground focus:outline-none">
                {faq.question}
                <ChevronDownIcon className="ml-2 h-5 w-5 transition-transform duration-200 group-data-[state=open]:rotate-180" />
              </Accordion.Trigger>
            </Accordion.Header>
            <Accordion.Content className="px-6 pb-5 text-muted-foreground text-base animate-fadeIn">
              {faq.answer}
            </Accordion.Content>
          </Accordion.Item>
        ))}
      </Accordion.Root>
    </section>
  );
}
