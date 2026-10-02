// Who may embed /embed in an iframe. "*" = any site (fine for a demo); set EMBED_ANCESTORS in production,
// e.g. EMBED_ANCESTORS="https://client-site.com https://www.client-site.com"
const ancestors = process.env.EMBED_ANCESTORS || "*";

export default {
  async headers() {
    return [{ source: "/embed", headers: [{ key: "Content-Security-Policy", value: `frame-ancestors ${ancestors}` }] }];
  },
};
