import https from 'https';
import { execSync } from 'child_process';

try {
  const remoteUrl = execSync('git remote get-url origin').toString().trim();
  const match = remoteUrl.match(/github\.com[:/](.+?)(?:\.git)?$/);
  if (!match) throw new Error('Could not parse GitHub repo from remote URL');
  const repo = match[1];

  const branch = execSync('git rev-parse --abbrev-ref HEAD').toString().trim();
  const sha = execSync('git rev-parse HEAD').toString().trim();

  let githubToken = '';
  try {
    const credInput = 'protocol=https\nhost=github.com\n\n';
    const credOutput = execSync('git credential fill', { input: credInput }).toString();
    const pwdMatch = credOutput.match(/password=(.+)/);
    if (pwdMatch) {
      githubToken = pwdMatch[1].trim();
    }
  } catch (e) {
    console.warn('Could not extract Git credentials for GitHub API.');
  }

  console.log(`Monitoring CI for ${repo} on branch ${branch} (commit ${sha.slice(0,7)})...`);

  const headers = { 'User-Agent': 'Node.js' };
  if (githubToken) {
    headers['Authorization'] = `Bearer ${githubToken}`;
  }

  const checkStatus = () => {
    https.get(`https://api.github.com/repos/${repo}/actions/runs?branch=${branch}&per_page=10`, {
      headers
    }, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          
          if (json.message === 'Not Found' && !githubToken) {
            console.warn('\n⚠️ GitHub Action monitoring skipped: Repository is private and no valid auth token was found.');
            process.exit(0);
          } else if (json.message === 'Not Found') {
            console.warn('\n⚠️ GitHub Action monitoring skipped: Repository not found (token may not have repo scope).');
            process.exit(0);
          }

          if (json.message && json.status !== '200') {
            console.warn(`\n⚠️ GitHub API error: ${json.message}`);
            process.exit(0);
          }

          const run = json.workflow_runs?.find(r => r.head_sha === sha);
          
          if (!run) {
            console.log('Waiting for GitHub Action to start...');
            setTimeout(checkStatus, 5000);
            return;
          }

          if (run.status === 'completed') {
            console.log(`\nGitHub Action completed with conclusion: ${run.conclusion.toUpperCase()}`);
            console.log(`View logs here: ${run.html_url}`);
            if (run.conclusion === 'success') {
              process.exit(0);
            } else {
              console.error('\nCI Failed! The agent MUST fix the errors before proceeding.');
              process.exit(1);
            }
          } else {
            process.stdout.write(`\rStatus: ${run.status}...`);
            setTimeout(checkStatus, 5000);
          }
        } catch(e) {
          console.error('Error parsing GitHub API response:', e.message);
          setTimeout(checkStatus, 5000);
        }
      });
    }).on('error', (e) => {
      console.error('HTTP Request Error:', e.message);
      setTimeout(checkStatus, 5000);
    });
  };

  checkStatus();
} catch (e) {
  console.error(e.message);
  process.exit(1);
}
