<?php

namespace App\Http\Controllers;

use App\Http\Controllers\Controller;
use Illuminate\Http\Request;
use App\Models\Company;
use App\Models\Contact;
use App\Models\TechnologyDetection;
use App\Services\Crawler\PoliteCrawler;
use App\Services\TechDetector\FingerprintEngine;
use App\Services\Extractor\ContactExtractor;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class DiscoveryController extends Controller
{
    public function search(Request $request)
    {
        $workspace = $request->active_workspace;
        $query = Company::where('workspace_id', $workspace->id)->with(['contacts', 'detections']);

        // 1. Text Search Query
        if ($search = $request->input('query')) {
            $query->where(function ($q) use ($search) {
                $q->where('legal_name', 'like', "%{$search}%")
                  ->orWhere('domain', 'like', "%{$search}%")
                  ->orWhere('industry', 'like', "%{$search}%");
            });
        }

        // 2. Filters
        if ($country = $request->input('country')) {
            $query->where('hq_country', $country);
        }

        if ($industry = $request->input('industry')) {
            $query->where('industry', $industry);
        }

        // Has Email filter
        if ($request->boolean('has_email')) {
            $query->whereHas('contacts', function ($q) {
                $q->whereNotNull('email');
            });
        }

        // Has Phone filter
        if ($request->boolean('has_phone')) {
            $query->whereHas('contacts', function ($q) {
                $q->whereNotNull('phone');
            });
        }

        // Tech filters (AND match)
        if ($techs = $request->input('techs')) {
            if (is_array($techs)) {
                foreach ($techs as $tech) {
                    $query->whereHas('detections', function ($q) use ($tech) {
                        $q->where('technology_name', $tech);
                    });
                }
            }
        }

        // Use pagination (100 per page)
        $paginator = $query->orderBy('confidence_score', 'desc')->paginate(100);

        return response()->json([
            'status' => 'success',
            'data' => $paginator->items(),
            'current_page' => $paginator->currentPage(),
            'last_page' => $paginator->lastPage(),
            'total' => $paginator->total(),
            'has_more' => $paginator->hasMorePages()
        ]);
    }

    /**
     * Start a background discovery and scan job.
     */
    public function startScan(Request $request)
    {
        $workspace = $request->active_workspace;
        
        $request->validate([
            'keyword' => 'required|string',
            'location' => 'required|string',
        ]);

        $keyword = trim($request->input('keyword'));
        $location = trim($request->input('location'));

        // Initialize discoverer
        $discoverer = new \App\Services\Discovery\LeadDiscoverer();
        $domains = $discoverer->discover($keyword, $location);

        if (empty($domains)) {
            return response()->json([
                'status' => 'failed',
                'error' => "No public websites found for keyword '{$keyword}' in '{$location}'."
            ]);
        }

        // We will scan the discovered domains (up to 15 to keep it fast and cPanel safe)
        $crawler = new PoliteCrawler();
        $scannedCount = 0;

        foreach ($domains as $domain) {
            $url = "https://{$domain}";
            $homeResponse = $crawler->crawl($url);
            if (!$homeResponse || empty($homeResponse['html'])) {
                $url = "http://{$domain}";
                $homeResponse = $crawler->crawl($url);
            }

            if ($homeResponse && !empty($homeResponse['html'])) {
                $html = $homeResponse['html'];
                $headers = $homeResponse['headers'] ?? [];

                // Detect Tech Stack
                $detections = FingerprintEngine::detect($html, $headers);

                // Extract Contacts (Emails, Socials, Name)
                $extracted = ContactExtractor::extract($html, $url);

                // Look for secondary pages (contact, about)
                $secondaryUrls = $this->findSecondaryLinks($html, $url);
                foreach ($secondaryUrls as $secUrl) {
                    $secResponse = $crawler->crawl($secUrl);
                    if ($secResponse && !empty($secResponse['html'])) {
                        // Merge extracted data
                        $secExtracted = ContactExtractor::extract($secResponse['html'], $secUrl);
                        $extracted['emails'] = array_values(array_unique(array_merge($extracted['emails'], $secExtracted['emails'])));
                        $extracted['phones'] = array_values(array_unique(array_merge($extracted['phones'], $secExtracted['phones'])));
                        $extracted['socials'] = array_merge($extracted['socials'], $secExtracted['socials']);
                        
                        // Add any extra tech detected
                        $secDetections = FingerprintEngine::detect($secResponse['html'], $secResponse['headers'] ?? []);
                        $detections = $this->mergeDetections($detections, $secDetections);
                    }
                }

                // Calculate confidence score
                $confidence = 0.3;
                if (!empty($extracted['emails'])) $confidence += 0.3;
                if (!empty($detections)) $confidence += 0.2;
                if ($extracted['legal_name'] !== 'Unknown Company') $confidence += 0.2;

                DB::transaction(function() use ($workspace, $domain, $extracted, $url, $confidence, $detections) {
                    $company = Company::updateOrCreate([
                        'workspace_id' => $workspace->id,
                        'domain' => $domain,
                    ], [
                        'legal_name' => $extracted['legal_name'] !== 'Unknown Company' ? $extracted['legal_name'] : ucfirst(explode('.', $domain)[0]),
                        'website_url' => $url,
                        'hq_country' => 'United Kingdom',
                        'confidence_score' => min($confidence, 1.0),
                        'last_scanned_at' => now(),
                    ]);

                    // Save Detections
                    TechnologyDetection::where('company_id', $company->id)->delete();
                    foreach ($detections as $det) {
                        TechnologyDetection::create([
                            'company_id' => $company->id,
                            'technology_name' => $det['technology_name'],
                            'category' => $det['category'],
                            'evidence' => $det['evidence'],
                            'matched_url' => $url,
                        ]);
                    }

                    // Save Contacts
                    Contact::where('company_id', $company->id)->delete();
                    foreach ($extracted['emails'] as $email) {
                        Contact::create([
                            'company_id' => $company->id,
                            'full_name' => 'General Inquiry',
                            'email' => $email,
                            'email_status' => 'verified',
                            'source_evidence' => 'Extracted from public site pages',
                        ]);
                    }

                    foreach ($extracted['phones'] as $phone) {
                        Contact::create([
                            'company_id' => $company->id,
                            'full_name' => 'Primary Phone',
                            'phone' => $phone,
                            'email_status' => 'unknown',
                            'source_evidence' => 'Extracted from site pages',
                        ]);
                    }
                });

                $scannedCount++;
            }
        }

        return response()->json([
            'status' => 'success',
            'scanned_count' => $scannedCount,
            'message' => "Successfully discovered and scanned {$scannedCount} businesses for '{$keyword}' in '{$location}'."
        ]);
    }

    /**
     * CSV Export of companies inside the workspace.
     */
    public function exportCsv(Request $request)
    {
        $workspace = $request->active_workspace;
        $companies = Company::where('workspace_id', $workspace->id)->with(['contacts', 'detections'])->get();

        $headers = [
            "Content-type"        => "text/csv",
            "Content-Disposition" => "attachment; filename=leadscope_leads.csv",
            "Pragma"              => "no-cache",
            "Cache-Control"       => "must-revalidate, post-check=0, pre-check=0",
            "Expires"             => "0"
        ];

        $columns = ['Company Name', 'Domain', 'Website', 'Confidence Score', 'Emails', 'Phones', 'Technologies'];

        $callback = function() use($companies, $columns) {
            $file = fopen('php://output', 'w');
            fputcsv($file, $columns);

            foreach ($companies as $company) {
                $emails = $company->contacts->pluck('email')->filter()->implode(', ');
                $phones = $company->contacts->pluck('phone')->filter()->implode(', ');
                $techs = $company->detections->pluck('technology_name')->implode(', ');

                fputcsv($file, [
                    $company->legal_name,
                    $company->domain,
                    $company->website_url,
                    $company->confidence_score * 100 . '%',
                    $emails,
                    $phones,
                    $techs
                ]);
            }

            fclose($file);
        };

        return response()->stream($callback, 200, $headers);
    }

    private function findSecondaryLinks(string $html, string $baseUrl): array
    {
        $crawler = new Crawler($html);
        $links = [];
        $patterns = ['/contact/i', '/about/i', '/team/i', '/terms/i', '/privacy/i'];

        $crawler->filter('a')->each(function ($node) use (&$links, $baseUrl, $patterns) {
            $href = $node->attr('href');
            if (!$href) return;

            // Make absolute
            if (str_starts_with($href, '/')) {
                $href = rtrim($baseUrl, '/') . $href;
            }

            if (str_starts_with($href, 'http')) {
                foreach ($patterns as $pattern) {
                    if (preg_match($pattern, $href)) {
                        $links[] = $href;
                        break;
                    }
                }
            }
        });

        return array_slice(array_unique($links), 0, 3); // limit to 3 subpages to be polite
    }

    private function mergeDetections(array $det1, array $det2): array
    {
        $merged = $det1;
        $names = array_column($det1, 'technology_name');
        foreach ($det2 as $d) {
            if (!in_array($d['technology_name'], $names)) {
                $merged[] = $d;
            }
        }
        return $merged;
    }
}
