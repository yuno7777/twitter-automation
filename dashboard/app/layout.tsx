import "./globals.css";
import type { Metadata } from "next";
import { Sidebar } from "@/components/sidebar";
import { Toaster } from "sonner";

export const metadata: Metadata = {
  title: "X Bot Dashboard",
  description: "Control center for the X automation bot",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="bg-bg text-white antialiased h-screen overflow-hidden">
        <div className="flex h-screen">
          <Sidebar />
          <main className="flex-1 p-6 md:p-10 overflow-y-auto overflow-x-hidden">{children}</main>
        </div>
        <Toaster theme="dark" position="bottom-right" richColors />
      </body>
    </html>
  );
}
