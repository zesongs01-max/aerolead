<?php

namespace App\Services\Discovery;

use GuzzleHttp\Client;
use Illuminate\Support\Facades\Log;

class LeadDiscoverer
{
    protected string $userAgent = 'LeadScope Bot (+https://leadscope-gtm.com/bot)';

    /**
     * Discovers domains from OSM and Search engine scrapers.
     */
    public function discover(string $keyword, string $location): array
    {
        $domains = [];

        // 1. Geocode location via Nominatim (OSM free geocoding)
        $coords = $this->geocode($location);
        if ($coords) {
            $osmDomains = $this->queryOverpass($keyword, $coords['lat'], $coords['lon']);
            $domains = array_merge($domains, $osmDomains);
        }

        // 2. Fallback search engine scraper (DuckDuckGo Lite)
        $searchDomains = $this->scrapeSearchEngine($keyword, $location);
        $domains = array_merge($domains, $searchDomains);

        return array_values(array_unique(array_filter($domains)));
    }

    protected function geocode(string $location): ?array
    {
        try {
            $client = new Client([
                'headers' => ['User-Agent' => $this->userAgent],
                'timeout' => 5
            ]);
            $res = $client->get('https://nominatim.openstreetmap.org/search', [
                'query' => [
                    'q' => $location,
                    'format' => 'json',
                    'limit' => 1
                ]
            ]);

            if ($res->getStatusCode() === 200) {
                $json = json_decode($res->getBody()->getContents(), true);
                if (!empty($json[0])) {
                    return [
                        'lat' => $json[0]['lat'],
                        'lon' => $json[0]['lon']
                    ];
                }
            }
        } catch (\Exception $e) {
            Log::error("Geocoding failed for {$location}: " . $e->getMessage());
        }

        return null;
    }

    protected function queryOverpass(string $keyword, string $lat, string $lon): array
    {
        $domains = [];
        // Map keyword to OSM shop/office tags
        $category = 'fashion';
        if (str_contains(strtolower($keyword), 'food') || str_contains(strtolower($keyword), 'restaurant')) {
            $category = 'restaurant';
        } else if (str_contains(strtolower($keyword), 'tech') || str_contains(strtolower($keyword), 'software')) {
            $category = 'office';
        }

        // Overpass QL: 15km radius
        $query = '[out:json][timeout:15];
        (
          node["website"](around:15000,' . $lat . ',' . $lon . ');
          way["website"](around:15000,' . $lat . ',' . $lon . ');
        );
        out tags;';

        try {
            $client = new Client([
                'headers' => ['User-Agent' => $this->userAgent],
                'timeout' => 10
            ]);
            $res = $client->post('https://overpass-api.de/api/interpreter', [
                'body' => $query
            ]);

            if ($res->getStatusCode() === 200) {
                $json = json_decode($res->getBody()->getContents(), true);
                if (!empty($json['elements'])) {
                    foreach ($json['elements'] as $el) {
                        if (!empty($el['tags']['website'])) {
                            $web = $el['tags']['website'];
                            $domain = $this->cleanDomain($web);
                            if ($domain) {
                                $domains[] = $domain;
                            }
                        }
                    }
                }
            }
        } catch (\Exception $e) {
            Log::error("Overpass query failed: " . $e->getMessage());
        }

        return array_slice(array_unique($domains), 0, 15);
    }

    protected function scrapeSearchEngine(string $keyword, string $location): array
    {
        $domains = [];
        $query = urlencode("{$keyword} {$location} website");
        $url = "https://html.duckduckgo.com/html/?q={$query}";

        try {
            $client = new Client([
                'headers' => [
                    'User-Agent' => 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
                    'Accept-Language' => 'en-US,en;q=0.9',
                ],
                'timeout' => 8
            ]);

            $res = $client->get($url);
            if ($res->getStatusCode() === 200) {
                $html = $res->getBody()->getContents();
                // Find all result links
                preg_match_all('/class="result__url"[^>]*>\s*([^<\s]+)/', $html, $matches);
                if (!empty($matches[1])) {
                    foreach ($matches[1] as $match) {
                        $domain = $this->cleanDomain(trim($match));
                        if ($domain && !str_contains($domain, 'duckduckgo.com')) {
                            $domains[] = $domain;
                        }
                    }
                }
            }
        } catch (\Exception $e) {
            Log::error("DuckDuckGo scraping failed: " . $e->getMessage());
        }

        return array_slice(array_unique($domains), 0, 15);
    }

    private function cleanDomain(string $url): ?string
    {
        $url = trim($url);
        if (!str_starts_with($url, 'http')) {
            $url = 'http://' . $url;
        }

        $parts = parse_url($url);
        if (empty($parts['host'])) {
            return null;
        }

        $host = strtolower($parts['host']);
        // Strip www.
        if (str_starts_with($host, 'www.')) {
            $host = substr($host, 4);
        }

        return $host;
    }
}
