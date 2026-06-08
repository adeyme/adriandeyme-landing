const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i;
const BREVO_LIST_ID = 3; // Lista "La Escucha" en Brevo

// Parse defensivo: el body puede venir como objeto (Vercel lo parsea) o como string
function parseBody(body) {
  if (!body) return {};
  if (typeof body === 'object') return body;
  try {
    return JSON.parse(body);
  } catch {
    return {};
  }
}

export default async function handler(req, res) {
  // Solo POST
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const body = parseBody(req.body);
  const email = String(body.email || '').trim().toLowerCase();

  // Honeypot: los usuarios reales no completan este campo oculto.
  // Si viene relleno, respondemos ok sin registrar nada (descarte silencioso).
  if (body.website) {
    return res.status(200).json({ ok: true });
  }

  // Validación de email (regex + límite de longitud)
  if (!EMAIL_RE.test(email) || email.length > 254) {
    return res.status(400).json({ error: 'Email inválido' });
  }

  const apiKey = process.env.BREVO_API_KEY;
  if (!apiKey) {
    console.error('BREVO_API_KEY no configurada');
    return res.status(500).json({ error: 'No pudimos procesar la solicitud' });
  }

  try {
    const response = await fetch('https://api.brevo.com/v3/contacts', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'api-key': apiKey,
      },
      body: JSON.stringify({
        email,
        listIds: [BREVO_LIST_ID],
        updateEnabled: true, // Si ya existe, lo actualiza sin error
      }),
    });

    // 201 = creado, 204 = actualizado — ambos son éxito
    if (response.status === 201 || response.status === 204) {
      return res.status(200).json({ ok: true });
    }

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = { status: response.status };
    }

    // El detalle se registra en logs, no se expone al cliente
    console.error('Brevo error:', data);
    return res.status(500).json({ error: 'No pudimos registrar el contacto' });
  } catch (err) {
    console.error('Brevo fetch error:', err);
    return res.status(500).json({ error: 'Error de conexión' });
  }
}
