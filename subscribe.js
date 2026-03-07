export default async function handler(req, res) {
  // Solo POST
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { email } = req.body;

  // Validación básica
  if (!email || !email.includes('@')) {
    return res.status(400).json({ error: 'Email inválido' });
  }

  const apiKey = process.env.BREVO_API_KEY;
  if (!apiKey) {
    return res.status(500).json({ error: 'API key no configurada' });
  }

  try {
    const response = await fetch('https://api.brevo.com/v3/contacts', {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'api-key': apiKey,
      },
      body: JSON.stringify({
        email: email,
        listIds: [3],          // ID lista "La Escucha" en Brevo
        updateEnabled: true,   // Si ya existe, lo actualiza sin error
      }),
    });

    // 201 = creado, 204 = actualizado — ambos son éxito
    if (response.status === 201 || response.status === 204) {
      return res.status(200).json({ ok: true });
    }

    const data = await response.json();
    console.error('Brevo error:', data);
    return res.status(500).json({ error: 'Error al registrar el contacto' });

  } catch (err) {
    console.error('Fetch error:', err);
    return res.status(500).json({ error: 'Error de conexión' });
  }
}
