import { posix } from "node:path";
import type { Plugin, ViteDevServer, PreviewServer } from "vite";

// Private model deliveries are never SPA routes. Reject before Vite's static
// handler (which includes local filesystem paths in its default 403 page).
export function pcbPrivateAssets(): Plugin {
  const install = (server: ViteDevServer | PreviewServer) => {
    server.middlewares.use((request, response, next) => {
      let pathname = (request.url || "/").split("?", 1)[0];
      try {
        for (let i = 0; i < 6; i++) {
          const decoded = decodeURIComponent(pathname);
          if (decoded === pathname) break;
          pathname = decoded;
        }
      } catch {
        // A malformed URL cannot identify an allowed application resource.
        pathname = "/assets/pcb/invalid-url";
      }
      // Win32 treats trailing dots/spaces as directory aliases. Normalize them
      // too, while retaining actual dot segments for traversal normalization.
      pathname = pathname.replaceAll("\\", "/").split("/")
        .map(segment => segment === "." || segment === ".." ? segment : segment.replace(/[. ]+$/, ""))
        .join("/");
      pathname = posix.normalize(pathname).toLowerCase();
      if (!/(?:^|\/)assets\/(?:pcb|pcb_segment|pcb_fenlei|pcb_classification)(?:\/|$)/.test(pathname)
          && !/(?:^|\/)packages\/infer\/pcb_classification(?:\/|$)/.test(pathname)) return next();
      response.statusCode = 403;
      response.setHeader("Content-Type", "text/plain; charset=utf-8");
      response.setHeader("Cache-Control", "no-store");
      response.setHeader("X-Content-Type-Options", "nosniff");
      response.end(request.method === "HEAD" ? undefined : "Forbidden");
    });
  };
  return { name: "pcb-private-assets", enforce: "pre", configureServer: install, configurePreviewServer: install };
}
