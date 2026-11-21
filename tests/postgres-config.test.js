import {test} from 'node:test';
import assert from 'node:assert/strict';
import {postgresOptions} from '../lib/postgres-config.js';
test('database URLs cannot disable TLS certificate verification',()=>{
 const options=postgresOptions('postgresql://user:password@example.com/db?sslmode=no-verify&ssl=false&uselibpqcompat=true&application_name=test');
 const url=new URL(options.connectionString);
 assert.equal(options.ssl.rejectUnauthorized,true);
 assert.equal(url.searchParams.has('sslmode'),false);
 assert.equal(url.searchParams.has('ssl'),false);
 assert.equal(url.searchParams.has('uselibpqcompat'),false);
 assert.equal(url.searchParams.get('application_name'),'test');
 assert.equal(options.statement_timeout,15000);
});
test('session-scoped schema and locks use Neon direct endpoint, not transaction pooler',()=>{
 const url=new URL(postgresOptions('postgresql://u:p@ep-example-pooler.eu-central-1.aws.neon.tech/db').connectionString);
 assert.equal(url.hostname,'ep-example.eu-central-1.aws.neon.tech');
 assert.equal(new URL(postgresOptions('postgresql://u:p@pooler.example.com/db').connectionString).hostname,'pooler.example.com');
});
