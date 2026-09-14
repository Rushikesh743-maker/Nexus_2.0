import { createClient } from '@supabase/supabase-js';

const url = 'https://gpycgjkakeeqygilrztx.supabase.co';
const anonKey = 'sb_publishable_MqB-rmbrnGD7DcGqHU37Hg_0jcGOIMA';
const supabase = createClient(url, anonKey);

async function test(email, password){
  const { data, error } = await supabase.auth.signUp({ email, password });
  console.log('SignUp Data:', data);
  console.error('SignUp Error:', error);
}

// Use a random email each time to avoid conflict
const random = Math.random().toString(36).substring(2,10);
const email = `test_${random}@example.com`;
const password = 'Test123!';

test(email, password);
