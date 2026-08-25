import * as React from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { cn } from "@/lib/utils";

interface ToastMessage {
  id: number;
  text: string;
  variant: "default" | "success" | "error";
}

interface ToastContextValue {
  toast: (text: string, variant?: ToastMessage["variant"]) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function useToast() {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx.toast;
}

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = React.useState<ToastMessage[]>([]);

  const toast = React.useCallback((text: string, variant: ToastMessage["variant"] = "default") => {
    const id = nextId++;
    setMessages((m) => [...m, { id, text, variant }]);
  }, []);

  const dismiss = (id: number) => setMessages((m) => m.filter((msg) => msg.id !== id));

  return (
    <ToastContext.Provider value={{ toast }}>
      <ToastPrimitive.Provider swipeDirection="down" duration={2200}>
        {children}
        {messages.some((m) => m.variant === "success") && (
          <div className="fixed inset-0 z-[99] bg-black/50" />
        )}
        {messages.map((m) => (
          <ToastPrimitive.Root
            key={m.id}
            onOpenChange={(open) => !open && dismiss(m.id)}
            className={cn(
              "border backdrop-blur",
              "data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
              m.variant === "success" &&
                "rounded-xl border-primary/40 bg-card px-10 py-6 text-center font-heading text-lg font-bold text-primary shadow-2xl data-[state=open]:zoom-in-95",
              m.variant === "error" &&
                "border-destructive/30 bg-destructive/15 px-4 py-2.5 font-mono text-xs text-destructive data-[state=open]:slide-in-from-bottom-2",
              m.variant === "default" &&
                "border-border bg-card px-4 py-2.5 font-mono text-xs text-foreground data-[state=open]:slide-in-from-bottom-2",
            )}
          >
            <ToastPrimitive.Description>{m.text}</ToastPrimitive.Description>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport
          className={cn(
            "fixed z-[100] flex flex-col items-center gap-2",
            messages.some((m) => m.variant === "success")
              ? "inset-0 justify-center"
              : "inset-x-0 bottom-[calc(var(--nav-h)+16px+env(safe-area-inset-bottom))] mx-auto w-fit max-w-[90vw]",
          )}
        />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}
