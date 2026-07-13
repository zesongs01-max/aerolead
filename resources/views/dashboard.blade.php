@extends('layouts.app')

@section('body')
<div class="h-screen flex overflow-hidden bg-slate-50" x-data="dashboardState()" x-init="init()">
    
    <!-- Left Navigation Sidebar -->
    <div class="hidden md:flex md:flex-shrink-0">
        <div class="flex flex-col w-64 border-r border-slate-200/80 bg-white">
            <div class="flex flex-col flex-grow pt-5 pb-4 overflow-y-auto">
                
                <!-- Brand logo -->
                <div class="flex items-center flex-shrink-0 px-4 mb-6">
                    <span class="text-xl font-bold text-navy-900 tracking-tight flex items-center gap-2">
                        <i class="fa-solid fa-crosshairs text-primary"></i> LeadScope
                    </span>
                </div>

                <!-- Active User & Workspace Info -->
                <div class="px-4 mb-6">
                    <div class="bg-navy-50/60 p-3 rounded-lg border border-navy-100/50">
                        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Active Workspace</div>
                        <div class="text-sm font-bold text-navy-900 truncate">{{ $workspace->name }}</div>
                        <div class="text-xs text-slate-500 mt-1 flex items-center gap-1">
                            <i class="fa-solid fa-user text-[10px]"></i> {{ Auth::user()->name }}
                        </div>
                    </div>
                </div>

                <!-- Navigation links -->
                <nav class="flex-1 px-2 space-y-1 bg-white">
                    <a href="#" class="bg-slate-100 text-navy-900 group flex items-center px-2 py-2 text-sm font-semibold rounded-md transition-all">
                        <i class="fa-solid fa-compass text-primary mr-3 text-base"></i> Discover Leads
                    </a>
                    <a href="#" class="text-slate-600 hover:bg-slate-50 hover:text-navy-900 group flex items-center px-2 py-2 text-sm font-medium rounded-md transition-all">
                        <i class="fa-solid fa-list-check text-slate-400 mr-3 text-base"></i> Saved Lists
                    </a>
                    <a href="#" class="text-slate-600 hover:bg-slate-50 hover:text-navy-900 group flex items-center px-2 py-2 text-sm font-medium rounded-md transition-all">
                        <i class="fa-solid fa-history text-slate-400 mr-3 text-base"></i> Search History
                    </a>
                </nav>
            </div>

            <!-- Sidebar Footer / Sign out -->
            <div class="flex-shrink-0 flex border-t border-slate-200/80 p-4 bg-slate-50/50">
                <form action="{{ route('logout') }}" method="POST" class="w-full">
                    @csrf
                    <button type="submit" class="w-full flex items-center justify-center gap-2 px-4 py-2 border border-slate-300 rounded-md text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 hover:text-red-600 shadow-sm transition-all">
                        <i class="fa-solid fa-right-from-bracket"></i> Sign Out
                    </button>
                </form>
            </div>
        </div>
    </div>

    <!-- Main Content Area -->
    <div class="flex flex-col w-0 flex-1 overflow-hidden">
        
        <!-- Header -->
        <header class="relative z-10 flex-shrink-0 flex h-16 bg-white border-b border-slate-200/80 shadow-sm">
            <div class="flex-1 px-4 flex justify-between">
                <div class="flex-1 flex items-center">
                    
                    <!-- Search Input -->
                    <div class="w-full max-w-lg lg:max-w-xs relative">
                        <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                            <i class="fa-solid fa-magnifying-glass text-slate-400"></i>
                        </div>
                        <input x-model="searchQuery" @input.debounce.300ms="triggerSearch()"
                            class="block w-full pl-10 pr-3 py-2 border border-slate-300 rounded-md leading-5 bg-white placeholder-slate-400 focus:outline-none focus:placeholder-slate-500 focus:ring-1 focus:ring-primary focus:border-primary sm:text-sm" 
                            placeholder="Search legal name, domain, category..." type="search">
                    </div>

                </div>

                <!-- Right header info (User limits) -->
                <div class="ml-4 flex items-center md:ml-6 gap-6">
                    <div class="text-right">
                        <div class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Monthly Limit</div>
                        <div class="text-sm font-bold text-navy-900">{{ Auth::user()->scans_this_month }} / {{ Auth::user()->monthly_scan_limit }} domains</div>
                    </div>
                    <a href="{{ route('export') }}" class="inline-flex items-center gap-1.5 px-3 py-1.5 border border-primary text-xs font-semibold text-primary hover:bg-primary hover:text-white rounded-md transition-all shadow-sm">
                        <i class="fa-solid fa-download"></i> Export CSV
                    </a>
                </div>
            </div>
        </header>

        <!-- Main Body Workspace -->
        <main class="flex-1 relative overflow-y-auto focus:outline-none p-6 flex flex-col gap-6">
            
            <!-- Quick stats row -->
            <div class="grid grid-cols-1 md:grid-cols-3 gap-5">
                <div class="bg-white p-5 rounded-xl border border-slate-200/80 shadow-sm flex items-center gap-4">
                    <div class="p-3 bg-blue-50 text-primary rounded-lg">
                        <i class="fa-solid fa-building text-xl"></i>
                    </div>
                    <div>
                        <div class="text-xs text-slate-400 font-semibold uppercase tracking-wider">Discovered Companies</div>
                        <div class="text-2xl font-bold text-navy-900">{{ $companiesCount }}</div>
                    </div>
                </div>

                <div class="bg-white p-5 rounded-xl border border-slate-200/80 shadow-sm flex items-center gap-4">
                    <div class="p-3 bg-emerald-50 text-emerald-600 rounded-lg">
                        <i class="fa-solid fa-envelope text-xl"></i>
                    </div>
                    <div>
                        <div class="text-xs text-slate-400 font-semibold uppercase tracking-wider">Extracted Contacts</div>
                        <div class="text-2xl font-bold text-navy-900">{{ $contactsCount }}</div>
                    </div>
                </div>

                <div class="bg-white p-5 rounded-xl border border-slate-200/80 shadow-sm flex items-center gap-4">
                    <div class="p-3 bg-purple-50 text-purple-600 rounded-lg">
                        <i class="fa-solid fa-laptop-code text-xl"></i>
                    </div>
                    <div>
                        <div class="text-xs text-slate-400 font-semibold uppercase tracking-wider">Unique Technologies</div>
                        <div class="text-2xl font-bold text-navy-900">{{ $techsCount }}</div>
                    </div>
                </div>
            </div>

            <!-- Domain discovery entry panel -->
            <div class="bg-white p-5 rounded-xl border border-slate-200/80 shadow-sm">
                <h3 class="text-sm font-bold text-navy-900 uppercase tracking-wider mb-3">Discover B2B Leads from the Web</h3>
                <form @submit.prevent="triggerScan()" class="flex flex-col md:flex-row gap-3">
                    <div class="flex-grow max-w-sm relative">
                        <label class="block text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Keyword / Industry</label>
                        <input x-model="discoverKeyword" required
                            class="block w-full px-3 py-2 border border-slate-300 rounded-md leading-5 bg-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary sm:text-sm"
                            placeholder="e.g. fashion boutique">
                    </div>
                    <div class="flex-grow max-w-sm relative">
                        <label class="block text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1">City / Location</label>
                        <input x-model="discoverLocation" required
                            class="block w-full px-3 py-2 border border-slate-300 rounded-md leading-5 bg-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary sm:text-sm"
                            placeholder="e.g. Manchester">
                    </div>
                    <div class="flex items-end">
                        <button type="submit" :disabled="scanLoading"
                            class="inline-flex items-center justify-center gap-2 px-6 py-2.5 border border-transparent text-sm font-semibold rounded-md text-white bg-primary hover:bg-blue-700 disabled:bg-blue-300 shadow-sm transition-all h-[38px]">
                            <template x-if="scanLoading">
                                <i class="fa-solid fa-spinner fa-spin mr-1"></i>
                            </template>
                            <span x-text="scanLoading ? 'Discovering & Scanning...' : 'Discover Leads'"></span>
                        </button>
                    </div>
                </form>
                
                <!-- Status logs -->
                <div class="mt-3 text-sm" x-show="scanError || scanSuccess">
                    <div class="p-3 bg-red-50 text-red-700 border border-red-200/60 rounded-md flex items-center gap-2" x-show="scanError">
                        <i class="fa-solid fa-circle-exclamation text-red-500"></i>
                        <span x-text="scanError"></span>
                    </div>
                    <div class="p-3 bg-green-50 text-green-700 border border-green-200/60 rounded-md flex items-center gap-2" x-show="scanSuccess">
                        <i class="fa-solid fa-circle-check text-green-500"></i>
                        <span x-text="scanSuccess"></span>
                    </div>
                </div>
            </div>

            <!-- Workspace split-view: Filters/Table vs Detail Card -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
                
                <!-- Filters and Results Column -->
                <div class="lg:col-span-2 flex flex-col gap-6">
                    
                    <!-- Filters drawer inline -->
                    <div class="bg-white p-5 rounded-xl border border-slate-200/80 shadow-sm">
                        <div class="flex justify-between items-center mb-4">
                            <h3 class="text-sm font-bold text-navy-900 uppercase tracking-wider flex items-center gap-1.5">
                                <i class="fa-solid fa-filter text-slate-400"></i> Search Filters
                            </h3>
                            <button @click="resetFilters()" class="text-xs font-semibold text-primary hover:text-blue-700">Reset Filters</button>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                            
                            <!-- Country filter -->
                            <div>
                                <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Country</label>
                                <select x-model="filters.country" @change="triggerSearch()"
                                    class="block w-full py-1.5 px-3 border border-slate-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-primary focus:border-primary sm:text-sm">
                                    <option value="">All Countries</option>
                                    <option value="United Kingdom">United Kingdom</option>
                                    <option value="United States">United States</option>
                                </select>
                            </div>

                            <!-- Industry filter -->
                            <div>
                                <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">Industry</label>
                                <select x-model="filters.industry" @change="triggerSearch()"
                                    class="block w-full py-1.5 px-3 border border-slate-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-primary focus:border-primary sm:text-sm">
                                    <option value="">All Industries</option>
                                    <option value="Fashion">Fashion</option>
                                    <option value="Retail">Retail</option>
                                    <option value="Technology">Technology</option>
                                </select>
                            </div>

                            <!-- Data check boxes -->
                            <div class="flex flex-col gap-2 justify-center pt-4">
                                <label class="inline-flex items-center text-sm text-slate-700">
                                    <input type="checkbox" x-model="filters.has_email" @change="triggerSearch()" class="h-4 w-4 text-primary border-slate-300 rounded">
                                    <span class="ml-2">Has Email Address</span>
                                </label>
                                <label class="inline-flex items-center text-sm text-slate-700">
                                    <input type="checkbox" x-model="filters.has_phone" @change="triggerSearch()" class="h-4 w-4 text-primary border-slate-300 rounded">
                                    <span class="ml-2">Has Phone Number</span>
                                </label>
                            </div>

                        </div>

                        <!-- Tech categories multi-filter -->
                        <div class="mt-4 border-t border-slate-100 pt-4">
                            <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Technologies Used (AND)</label>
                            <div class="flex flex-wrap gap-2">
                                <template x-for="tech in allTechs" :key="tech">
                                    <button @click="toggleTech(tech)"
                                        :class="filters.techs.includes(tech) ? 'bg-primary text-white border-primary' : 'bg-slate-50 text-slate-700 border-slate-300 hover:bg-slate-100'"
                                        class="inline-flex items-center px-2.5 py-1 border rounded-md text-xs font-semibold tracking-wide transition-all select-none">
                                        <span x-text="tech"></span>
                                    </button>
                                </template>
                            </div>
                        </div>

                    </div>

                    <!-- Company Table -->
                    <div class="bg-white rounded-xl border border-slate-200/80 shadow-sm overflow-hidden">
                        <table class="min-w-full divide-y divide-slate-200">
                            <thead class="bg-slate-50">
                                <tr>
                                    <th scope="col" class="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Company</th>
                                    <th scope="col" class="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Target Domain</th>
                                    <th scope="col" class="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Confidence</th>
                                    <th scope="col" class="px-6 py-3 text-left text-xs font-bold text-slate-400 uppercase tracking-wider">Technologies</th>
                                </tr>
                            </thead>
                            <tbody class="bg-white divide-y divide-slate-100">
                                <template x-for="comp in companies" :key="comp.id">
                                    <tr @click="selectCompany(comp)" 
                                        :class="selectedCompany && selectedCompany.id === comp.id ? 'bg-blue-50/40' : 'hover:bg-slate-50/50'"
                                        class="cursor-pointer transition-all">
                                        <td class="px-6 py-4 whitespace-nowrap">
                                            <div class="text-sm font-bold text-navy-900" x-text="comp.legal_name"></div>
                                            <div class="text-xs text-slate-400" x-text="comp.hq_country"></div>
                                        </td>
                                        <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-600">
                                            <span x-text="comp.domain"></span>
                                        </td>
                                        <td class="px-6 py-4 whitespace-nowrap">
                                            <span :class="comp.confidence_score >= 0.7 ? 'bg-green-50 text-green-700 border-green-200' : 'bg-amber-50 text-amber-700 border-amber-200'"
                                                class="px-2 py-0.5 inline-flex text-xs leading-5 font-semibold rounded-full border"
                                                x-text="Math.round(comp.confidence_score * 100) + '%'">
                                            </span>
                                        </td>
                                        <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">
                                            <div class="flex gap-1.5 flex-wrap">
                                                <template x-for="det in comp.detections.slice(0, 3)" :key="det.id">
                                                    <span class="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-[10px] font-semibold uppercase tracking-wider" x-text="det.technology_name"></span>
                                                </template>
                                                <span class="text-slate-400 text-xs" x-show="comp.detections.length > 3" x-text="'+' + (comp.detections.length - 3)"></span>
                                            </div>
                                        </td>
                                    </tr>
                                </template>
                                <tr x-show="companies.length === 0">
                                    <td colspan="4" class="px-6 py-12 text-center text-slate-400">
                                        <i class="fa-solid fa-folder-open text-3xl mb-2 block"></i>
                                        No leads found matching your criteria.
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                        
                        <!-- Pagination Bar -->
                        <div class="bg-white px-4 py-3 flex items-center justify-between border-t border-slate-200 sm:px-6" x-show="lastPage > 1">
                            <div class="flex-1 flex justify-between sm:hidden">
                                <button @click="changePage(currentPage - 1)" :disabled="currentPage === 1" class="relative inline-flex items-center px-4 py-2 border border-slate-300 text-sm font-semibold rounded-md text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-50 select-none">
                                    Previous
                                </button>
                                <button @click="changePage(currentPage + 1)" :disabled="currentPage === lastPage" class="ml-3 relative inline-flex items-center px-4 py-2 border border-slate-300 text-sm font-semibold rounded-md text-slate-700 bg-white hover:bg-slate-50 disabled:opacity-50 select-none">
                                    Next
                                </button>
                            </div>
                            <div class="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                                <div>
                                    <p class="text-sm text-slate-600">
                                        Showing page <span class="font-bold text-navy-900" x-text="currentPage"></span> of <span class="font-bold text-navy-900" x-text="lastPage"></span> (total <span class="font-bold text-navy-900" x-text="totalCount"></span> leads)
                                    </p>
                                </div>
                                <div>
                                    <nav class="relative z-0 inline-flex rounded-md shadow-sm -space-x-px" aria-label="Pagination">
                                        <button @click="changePage(currentPage - 1)" :disabled="currentPage === 1" class="relative inline-flex items-center px-2.5 py-1.5 rounded-l-md border border-slate-300 bg-white text-sm font-medium text-slate-500 hover:bg-slate-50 disabled:opacity-50 select-none">
                                            <i class="fa-solid fa-chevron-left text-xs"></i>
                                        </button>
                                        <button @click="changePage(currentPage + 1)" :disabled="currentPage === lastPage" class="relative inline-flex items-center px-2.5 py-1.5 rounded-r-md border border-slate-300 bg-white text-sm font-medium text-slate-500 hover:bg-slate-50 disabled:opacity-50 select-none">
                                            <i class="fa-solid fa-chevron-right text-xs"></i>
                                        </button>
                                    </nav>
                                </div>
                            </div>
                        </div>
                    </div>

                </div>

                <!-- Company Details Card Column -->
                <div class="lg:col-span-1">
                    
                    <div class="bg-white rounded-xl border border-slate-200/80 shadow-sm p-6 flex flex-col gap-6 sticky top-6" x-show="selectedCompany">
                        
                        <!-- Header Details -->
                        <div class="flex justify-between items-start border-b border-slate-100 pb-4">
                            <div>
                                <h2 class="text-lg font-bold text-navy-900" x-text="selectedCompany?.legal_name"></h2>
                                <a :href="selectedCompany?.website_url" target="_blank" class="text-xs text-primary font-medium hover:underline flex items-center gap-1 mt-1">
                                    <i class="fa-solid fa-up-right-from-square"></i> Visit Website
                                </a>
                            </div>
                            <span :class="selectedCompany?.confidence_score >= 0.7 ? 'bg-green-50 text-green-700 border-green-200' : 'bg-amber-50 text-amber-700 border-amber-200'"
                                class="px-2 py-1 text-xs font-semibold rounded-md border text-center"
                                x-text="Math.round(selectedCompany?.confidence_score * 100) + '% Confidence'">
                            </span>
                        </div>

                        <!-- Sub-tab controls -->
                        <div class="flex border-b border-slate-100" x-data="{ tab: 'contacts' }">
                            <button @click="tab = 'contacts'" :class="tab === 'contacts' ? 'border-primary text-primary' : 'border-transparent text-slate-500 hover:text-slate-700'" class="flex-1 pb-2 text-xs font-bold uppercase tracking-wider border-b-2 text-center">
                                Contacts
                            </button>
                            <button @click="tab = 'techs'" :class="tab === 'techs' ? 'border-primary text-primary' : 'border-transparent text-slate-500 hover:text-slate-700'" class="flex-1 pb-2 text-xs font-bold uppercase tracking-wider border-b-2 text-center">
                                Techs
                            </button>
                            <button @click="tab = 'evidence'" :class="tab === 'evidence' ? 'border-primary text-primary' : 'border-transparent text-slate-500 hover:text-slate-700'" class="flex-1 pb-2 text-xs font-bold uppercase tracking-wider border-b-2 text-center">
                                Evidence
                            </button>

                            <!-- Tab Contents inside tabs mapping -->
                            <div class="w-full mt-4" x-show="tab === 'contacts'">
                                <h3 class="text-xs font-bold text-navy-900 uppercase tracking-wider mb-2">Discovered Contacts</h3>
                                <div class="flex flex-col gap-2 max-h-60 overflow-y-auto pr-1">
                                    <template x-for="contact in selectedCompany?.contacts" :key="contact.id">
                                        <div class="p-3 bg-slate-50 rounded-lg border border-slate-200/40 flex flex-col gap-1">
                                            <div class="text-xs font-semibold text-slate-400" x-text="contact.full_name"></div>
                                            <div class="text-sm font-bold text-navy-900 select-all" x-text="contact.email || contact.phone"></div>
                                            <div class="text-[10px] text-slate-400" x-text="contact.source_evidence"></div>
                                        </div>
                                    </template>
                                    <div class="text-xs text-slate-400 text-center py-4" x-show="!selectedCompany?.contacts || selectedCompany?.contacts.length === 0">
                                        No contacts extracted from this company's domain.
                                    </div>
                                </div>
                            </div>

                            <div class="w-full mt-4" x-show="tab === 'techs'">
                                <h3 class="text-xs font-bold text-navy-900 uppercase tracking-wider mb-2">Detected Stack</h3>
                                <div class="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
                                    <template x-for="det in selectedCompany?.detections" :key="det.id">
                                        <span class="inline-flex items-center px-2.5 py-1 bg-blue-50 text-primary border border-blue-100 rounded text-xs font-semibold tracking-wide uppercase" x-text="det.technology_name"></span>
                                    </template>
                                    <div class="text-xs text-slate-400 text-center py-4 w-full" x-show="!selectedCompany?.detections || selectedCompany?.detections.length === 0">
                                        No technologies detected.
                                    </div>
                                </div>
                            </div>

                            <div class="w-full mt-4" x-show="tab === 'evidence'">
                                <h3 class="text-xs font-bold text-navy-900 uppercase tracking-wider mb-2">Verification Logs</h3>
                                <div class="flex flex-col gap-2 max-h-60 overflow-y-auto pr-1">
                                    <template x-for="det in selectedCompany?.detections" :key="det.id">
                                        <div class="p-2.5 bg-slate-50 rounded border border-slate-200/50 text-xs">
                                            <div class="font-bold text-navy-900 uppercase" x-text="det.technology_name"></div>
                                            <div class="text-slate-500 mt-1" x-text="det.evidence"></div>
                                        </div>
                                    </template>
                                    <div class="text-xs text-slate-400 text-center py-4" x-show="!selectedCompany?.detections || selectedCompany?.detections.length === 0">
                                        No evidence logged.
                                    </div>
                                </div>
                            </div>
                        </div>

                    </div>

                    <div class="bg-white rounded-xl border border-slate-200/80 shadow-sm p-6 text-center text-slate-400" x-show="!selectedCompany">
                        <i class="fa-solid fa-circle-info text-2xl mb-2 block"></i>
                        Select a company from the list to view contacts, tech stack, and raw evidence.
                    </div>

                </div>

            </div>

        </main>
    </div>

</div>

<script>
    function dashboardState() {
        return {
            searchQuery: '',
            filters: {
                country: '',
                industry: '',
                has_email: false,
                has_phone: false,
                techs: []
            },
            companies: [],
            selectedCompany: null,
            discoverKeyword: '',
            discoverLocation: '',
            scanLoading: false,
            scanError: '',
            scanSuccess: '',
            currentPage: 1,
            lastPage: 1,
            totalCount: 0,
            allTechs: ['Shopify', 'WooCommerce', 'Magento', 'BigCommerce', 'Wix Stores', 'Squarespace Commerce', 'Klaviyo', 'Mailchimp', 'Omnisend', 'Brevo', 'HubSpot', 'ActiveCampaign'],

            init() {
                this.triggerSearch();
            },

            async triggerSearch() {
                const params = new URLSearchParams();
                if (this.searchQuery) params.append('query', this.searchQuery);
                if (this.filters.country) params.append('country', this.filters.country);
                if (this.filters.industry) params.append('industry', this.filters.industry);
                if (this.filters.has_email) params.append('has_email', '1');
                if (this.filters.has_phone) params.append('has_phone', '1');
                params.append('page', this.currentPage);
                this.filters.techs.forEach(t => params.append('techs[]', t));

                try {
                    const res = await fetch(`/search?${params.toString()}`);
                    const json = await res.json();
                    if (json.status === 'success') {
                        this.companies = json.data;
                        this.currentPage = json.current_page;
                        this.lastPage = json.last_page;
                        this.totalCount = json.total;
                        
                        // Keep selected company active if it still matches
                        if (this.selectedCompany) {
                            const found = this.companies.find(c => c.id === this.selectedCompany.id);
                            this.selectedCompany = found || null;
                        }
                    }
                } catch (e) {
                    console.error("Search request failed", e);
                }
            },

            async triggerScan() {
                this.scanLoading = true;
                this.scanError = '';
                this.scanSuccess = '';

                try {
                    const res = await fetch('/scan/start', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-TOKEN': '{{ csrf_token() }}'
                        },
                        body: JSON.stringify({ 
                            keyword: this.discoverKeyword, 
                            location: this.discoverLocation 
                        })
                    });
                    const data = await res.json();
                    
                    if (data.error) {
                        this.scanError = data.error;
                    } else if (data.status === 'failed') {
                        this.scanError = data.error;
                    } else if (data.status === 'success') {
                        this.scanSuccess = data.message;
                        this.discoverKeyword = '';
                        this.discoverLocation = '';
                        this.currentPage = 1;
                        await this.triggerSearch();
                    }
                } catch (e) {
                    this.scanError = 'An unexpected server error occurred during lead discovery.';
                } finally {
                    this.scanLoading = false;
                }
            },

            changePage(page) {
                if (page >= 1 && page <= this.lastPage) {
                    this.currentPage = page;
                    this.triggerSearch();
                }
            },

            selectCompany(company) {
                this.selectedCompany = company;
            },

            toggleTech(tech) {
                this.currentPage = 1;
                if (this.filters.techs.includes(tech)) {
                    this.filters.techs = this.filters.techs.filter(t => t !== tech);
                } else {
                    this.filters.techs.push(tech);
                }
                this.triggerSearch();
            },

            resetFilters() {
                this.currentPage = 1;
                this.filters.country = '';
                this.filters.industry = '';
                this.filters.has_email = false;
                this.filters.has_phone = false;
                this.filters.techs = [];
                this.triggerSearch();
            }
        }
    }
</script>
@endsection
