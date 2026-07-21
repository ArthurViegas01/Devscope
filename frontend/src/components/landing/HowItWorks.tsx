import { motion, type Variants } from "framer-motion";
import { Plug, Sparkles, Wrench } from "lucide-react";

import Card from "@/components/ui/Card";

const STEPS = [
  {
    icon: Plug,
    kicker: "01",
    title: "Connect over MCP",
    body: "The browser speaks the Model Context Protocol to a FastMCP server over streamable HTTP, the same protocol agents use.",
  },
  {
    icon: Wrench,
    kicker: "02",
    title: "Run typed tools",
    body: "Four tools fetch and analyse public GitHub data: profile stats, repository signals, job-fit, and a recruiter summary.",
  },
  {
    icon: Sparkles,
    kicker: "03",
    title: "Reason with an LLM",
    body: "A Groq-hosted LLM turns raw signals into candid, recruiter-grade insight, streamed back token by token.",
  },
];

const grid: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1 } },
};

const card: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
};

export default function HowItWorks() {
  return (
    <section className="py-12">
      <div className="mb-8 text-center">
        <h2 className="text-display-sm font-semibold text-ink-50">How it works</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-ink-300/70">
          A real MCP pipeline, not a mockup. Wired end to end.
        </p>
      </div>

      <motion.div
        variants={grid}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-80px" }}
        className="grid gap-4 sm:grid-cols-3"
      >
        {STEPS.map(({ icon: Icon, kicker, title, body }) => (
          <motion.div key={kicker} variants={card}>
            <Card interactive className="h-full p-6">
              <div className="mb-4 flex items-center justify-between">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-violet-400/20 bg-violet-500/10 text-violet-300">
                  <Icon className="h-5 w-5" />
                </span>
                <span className="font-mono text-xs text-ink-400/60">{kicker}</span>
              </div>
              <h3 className="text-base font-semibold text-ink-50">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-200/70">{body}</p>
            </Card>
          </motion.div>
        ))}
      </motion.div>
    </section>
  );
}
