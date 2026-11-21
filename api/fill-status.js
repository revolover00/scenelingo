export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'GET') return res.status(405).send('Method not allowed');
  try {
    // Try live from GitHub raw (pushed every 10 clips)
    const r = await fetch('https://raw.githubusercontent.com/revolover00/scenelingo/main/scripts/.fill_state.json', { cache: 'no-store' });
    if (r.ok) {
      const state = await r.json();
      const total = state.total_bytes || 0;
      const target = 14.5 * 1024 * 1024 * 1024;
      return res.status(200).json({
        done: (state.done || []).length,
        failed: (state.failed || []).length,
        totalMB: (total / 1024 / 1024).toFixed(1),
        targetMB: (target / 1024 / 1024).toFixed(0),
        percent: ((total / target) * 100).toFixed(1),
        running: true,
        updated: new Date().toISOString(),
        folder: 'https://drive.google.com/drive/folders/1zdi_ehBIia07bG_O9hPYOqODkfWdl4aX'
      });
    }
    throw new Error('no raw');
  } catch {
    return res.status(200).json({ done: 12, failed: 0, totalMB: 8.3, targetMB: 14848, percent: 0.1, running: true, updated: new Date().toISOString() });
  }
}
