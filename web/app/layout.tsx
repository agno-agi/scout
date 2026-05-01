import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Scout",
  description: "Your company intelligence agent",
};

// Inline script that runs before React hydrates — sets the dark class on
// <html> based on stored preference (or system preference) so users don't
// see a flash of the wrong theme.
const themeBootstrap = `
(function() {
  try {
    var stored = localStorage.getItem("scout:theme");
    var theme = stored === "dark" || stored === "light"
      ? stored
      : (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className="h-full font-sans">{children}</body>
    </html>
  );
}
