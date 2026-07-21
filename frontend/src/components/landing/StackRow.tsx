import { motion } from "framer-motion";

/** The production stack, grouped so the categories read at a glance. */
const STACK: Array<{ label: string; hint: string }> = [
  { label: "Python", hint: "Backend language" },
  { label: "FastMCP", hint: "MCP server framework" },
  { label: "Groq", hint: "LLM inference" },
  { label: "Redis", hint: "Caching + rate limiting" },
  { label: "React", hint: "TypeScript + Vite frontend" },
  { label: "Railway", hint: "Backend hosting" },
  { label: "Netlify", hint: "Frontend hosting" },
  { label: "Terraform", hint: "Infrastructure as Code" },
];

export default function StackRow() {
  return (
    <section className="py-12">
      <p className="text-center text-[11px] font-medium uppercase tracking-[0.18em] text-ink-400/60">
        Built with
      </p>
      <motion.ul
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-60px" }}
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.04 } } }}
        className="mx-auto mt-5 flex max-w-3xl flex-wrap items-center justify-center gap-2.5"
      >
        {STACK.map(({ label, hint }) => (
          <motion.li
            key={label}
            variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
            title={hint}
            className="rounded-full border border-violet-500/15 bg-white/[0.03] px-3.5 py-1.5 text-sm text-ink-200/80 transition-colors duration-200 hover:border-violet-400/30 hover:text-ink-50"
          >
            {label}
          </motion.li>
        ))}
      </motion.ul>
    </section>
  );
}
