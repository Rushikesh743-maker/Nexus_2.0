import { createClient } from '@supabase/supabase-js';

const url = 'https://gpycgjkakeeqygilrztx.supabase.co';
const anonKey = 'sb_publishable_MqB-rmbrnGD7DcGqHU37Hg_0jcGOIMA';
const supabase = createClient(url, anonKey);

async function test(email, password) {
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  console.log('Data:', data);
  console.error('Error:', error);
}

// Replace with actual credentials to test
test('nonexistent@example.com', 'test123');
