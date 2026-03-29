// Service worker handler for Web Share Target API.
// Intercepts POST to /share-target, caches the shared files,
// and redirects to the SPA route as a GET.

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (
    url.pathname === '/share-target' &&
    event.request.method === 'POST'
  ) {
    event.respondWith(handleShareTarget(event.request));
  }
});

async function handleShareTarget(request) {
  const formData = await request.formData();
  const cache = await caches.open('share-target-cache');

  // Collect shared files
  const files = formData.getAll('images');
  const title = formData.get('title') || '';
  const text = formData.get('text') || '';

  // Store metadata
  await cache.put(
    '/_share-meta',
    new Response(JSON.stringify({ title, text, fileCount: files.length }), {
      headers: { 'Content-Type': 'application/json' },
    }),
  );

  // Store each file
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const arrayBuffer = await file.arrayBuffer();
    await cache.put(
      `/_share-file-${i}`,
      new Response(arrayBuffer, {
        headers: {
          'Content-Type': file.type,
          'X-Filename': file.name,
        },
      }),
    );
  }

  // Redirect to the SPA route (GET)
  return Response.redirect('/share-target?received=1', 303);
}
