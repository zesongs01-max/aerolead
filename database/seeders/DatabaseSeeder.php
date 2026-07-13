<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        $user = User::create([
            'name' => 'LeadScope Admin',
            'email' => 'admin@leadscope.com',
            'password' => \Illuminate\Support\Facades\Hash::make('password123'),
            'role' => 'admin',
        ]);

        $workspace = \App\Models\Workspace::create([
            'name' => 'Default Workspace',
            'owner_id' => $user->id,
        ]);

        $user->active_workspace_id = $workspace->id;
        $user->save();
    }
}
