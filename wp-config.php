<?php
define( 'WP_CACHE', true );

/**
 * The base configuration for WordPress
 *
 * The wp-config.php creation script uses this file during the installation.
 * You don't have to use the web site, you can copy this file to "wp-config.php"
 * and fill in the values.
 *
 * This file contains the following configurations:
 *
 * * Database settings
 * * Secret keys
 * * Database table prefix
 * * Localized language
 * * ABSPATH
 *
 * @link https://wordpress.org/support/article/editing-wp-config-php/
 *
 * @package WordPress
 */

// ** Database settings - You can get this info from your web host ** //
/** The name of the database for WordPress */
define( 'DB_NAME', 'u167023529_ZlatR' );

/** Database username */
define( 'DB_USER', 'u167023529_4M5Vi' );

/** Database password */
define( 'DB_PASSWORD', 'YsoEhZZ2nv' );

/** Database hostname */
define( 'DB_HOST', '127.0.0.1' );

/** Database charset to use in creating database tables. */
define( 'DB_CHARSET', 'utf8' );

/** The database collate type. Don't change this if in doubt. */
define( 'DB_COLLATE', '' );

/**#@+
 * Authentication unique keys and salts.
 *
 * Change these to different unique phrases! You can generate these using
 * the {@link https://api.wordpress.org/secret-key/1.1/salt/ WordPress.org secret-key service}.
 *
 * You can change these at any point in time to invalidate all existing cookies.
 * This will force all users to have to log in again.
 *
 * @since 2.6.0
 */
define( 'AUTH_KEY',          'B9~WEtK23U}hXjE<o`H.fG|&|^OCI6gg:r`sf@)A2O-]1uo Xk!:L[*s};xJ*qQ`' );
define( 'SECURE_AUTH_KEY',   'O}SyOiXa{e6r|nQ5*:%,eZ}8}N2ot{:&Rq2 ?` Mv6>s82 Vu|QR.GjzQ?y~5>Q_' );
define( 'LOGGED_IN_KEY',     '$m]}E$Vnf}QV#%Y%0Xw6#8;W~9l5zSTT|k,M~CIpUk rT7 +AK-=:??y` 5G/[uE' );
define( 'NONCE_KEY',         '[QYPyGU:Vzz1]+b2THHppd9z=%=8#7&]Nn`4!S9i#4X9HgN/&-IWixBijdRRK#x(' );
define( 'AUTH_SALT',         '7B_&[q;$*%/i 3_.kn.mw,-=$Bn@#fH38k9g{wpD(?]0G^x9/x&X$|%L_sK%L&,F' );
define( 'SECURE_AUTH_SALT',  '[8VMj// ,K20Uyar6k`b50sxz:on(5pEEsOd[MxXwoNsZt+UTe)y2K#Xe5i=/Iu3' );
define( 'LOGGED_IN_SALT',    '3 ^Ix%5r0ym[[Y5L6 gzo<BY4%{__u*pFf=NI&KD.hhlP|X,?MxneZK<,Nfqt:*P' );
define( 'NONCE_SALT',        '=/H9^tTk`AHvomC2F[*J,B>Vy},FM^K[yRO%gUfN?m<ij]yr%6:i-! ;K<z=XU;t' );
define( 'WP_CACHE_KEY_SALT', '|ccY]/X5?N8wF1T3hi`*ik)lW(@iD<yv,X3Wb<S|{e0iEQsrW;m$S=vdAw-CraAK' );


/**#@-*/

/**
 * WordPress database table prefix.
 *
 * You can have multiple installations in one database if you give each
 * a unique prefix. Only numbers, letters, and underscores please!
 */
$table_prefix = 'wp_';


/* Add any custom values between this line and the "stop editing" line. */



/**
 * For developers: WordPress debugging mode.
 *
 * Change this to true to enable the display of notices during development.
 * It is strongly recommended that plugin and theme developers use WP_DEBUG
 * in their development environments.
 *
 * For information on other constants that can be used for debugging,
 * visit the documentation.
 *
 * @link https://wordpress.org/support/article/debugging-in-wordpress/
 */
if ( ! defined( 'WP_DEBUG' ) ) {
	define( 'WP_DEBUG', false );
}

define( 'FS_METHOD', 'direct' );
define( 'COOKIEHASH', '76a35d7cdb689dc52a89d3176dbaa4af' );
define( 'WP_AUTO_UPDATE_CORE', 'minor' );
define( 'DISABLE_WP_CRON', true ); // 由系統 cron 負責觸發，避免依賴訪客
/* That's all, stop editing! Happy publishing. */

/** Absolute path to the WordPress directory. */
if ( ! defined( 'ABSPATH' ) ) {
	define( 'ABSPATH', __DIR__ . '/' );
}

/** Sets up WordPress vars and included files. */
require_once ABSPATH . 'wp-settings.php';
