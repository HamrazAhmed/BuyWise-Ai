async page => {
  await page.route('**/api/analyze-requirements', route => route.fulfill({status:429,contentType:'application/json',headers:{'access-control-allow-origin':'http://localhost:3107'},body:JSON.stringify({error:{code:'RATE_LIMITED',message:'Quota reached',retry_after:17}})}))
  await page.goto('http://localhost:3107/')
  await page.getByLabel('Shopping request').fill('I need a laptop under 1000 USD')
  await page.getByRole('button',{name:'Start research',exact:true}).click()
  await page.getByText('Quota reached',{exact:false}).waitFor()
  await page.unroute('**/api/analyze-requirements')
  await page.route('**/api/comparison/outage-p4', route => route.abort())
  await page.goto('http://localhost:3107/results/outage-p4')
  await page.getByRole('button',{name:'Retry',exact:true}).waitFor()
  await page.unroute('**/api/comparison/outage-p4')
  await page.route('**/api/comparison/empty-p4', route => route.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'http://localhost:3107'},body:JSON.stringify({id:'empty-p4',created_at:new Date().toISOString(),requirement_analysis:[],notices:[],request_id:'empty',products:[],requirements:[],requirement_matches:{},tradeoffs:[],data_mode:'fixture'})}))
  await page.goto('http://localhost:3107/results/empty-p4')
  await page.getByText('No candidates found.',{exact:false}).waitFor()
  await page.unroute('**/api/comparison/empty-p4')
  return 'PASS: quota, backend outage and empty-result UI states'
}
